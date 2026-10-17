import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Any
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    select,
)
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./handwriter.db").strip().strip("'\"")

# Нормализация PostgreSQL URL для SQLAlchemy asyncpg (Render/Neon)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

if "sslmode=" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("sslmode=", "ssl=")

if "render.com" in DATABASE_URL and "ssl=" not in DATABASE_URL:
    sep = "&" if "?" in DATABASE_URL else "?"
    DATABASE_URL = f"{DATABASE_URL}{sep}ssl=require"

# Список ID администраторов (по умолчанию 1109865120)
ADMIN_IDS = {1109865120}
_admin_env = os.getenv("ADMIN_IDS", "1109865120")
if _admin_env:
    for _aid in str(_admin_env).split(","):
        _aid = _aid.strip()
        if _aid.isdigit():
            ADMIN_IDS.add(int(_aid))


def is_admin_id(tid: Optional[Any]) -> bool:
    """Безопасная проверка ID администратора/создателя."""
    if tid is None:
        return False
    try:
        return int(tid) in {int(x) for x in ADMIN_IDS}
    except (ValueError, TypeError):
        return False


engine_kwargs = {"echo": False}
if "sqlite" in DATABASE_URL:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 300

engine = create_async_engine(DATABASE_URL, **engine_kwargs)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(128), nullable=True)
    first_name = Column(String(128), nullable=True)
    is_pro = Column(Boolean, default=False, nullable=False)
    pro_expires_at = Column(DateTime, nullable=True)
    stars_spent = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")

    def check_pro_active(self) -> bool:
        """Проверяет, активен ли PRO-статус (для администратора всегда True)."""
        if is_admin_id(self.telegram_id):
            return True
        if not self.is_pro:
            return False
        if self.pro_expires_at is None:
            return True
        now = datetime.now(timezone.utc)
        expires = self.pro_expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires > now

    @property
    def is_admin(self) -> bool:
        return is_admin_id(self.telegram_id)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    telegram_payment_charge_id = Column(String(255), unique=True, index=True, nullable=False)
    provider_payment_charge_id = Column(String(255), nullable=True)
    plan_id = Column(String(64), nullable=False)
    stars_amount = Column(Integer, nullable=False)
    status = Column(String(32), default="completed", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="payments")


async def init_db():
    """Создание таблиц при старте сервера с отказоустойчивым переключением на SQLite."""
    global engine, AsyncSessionLocal
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("[DB] Tables initialized successfully.")
    except Exception as e:
        print(f"[DB WARN] Failed to initialize DB with {DATABASE_URL}: {e}")
        if "sqlite" not in DATABASE_URL:
            print("[DB] Automatically falling back to local SQLite database.")
            fallback_url = "sqlite+aiosqlite:///./handwriter.db"
            engine = create_async_engine(fallback_url, connect_args={"check_same_thread": False})
            AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            print("[DB] SQLite fallback ready.")


async def get_or_create_user(
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
) -> User:
    """Получить или зарегистрировать пользователя."""
    tid = int(telegram_id)
    is_adm = is_admin_id(tid)

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == tid))
        user = result.scalars().first()

        if not user:
            user = User(
                telegram_id=tid,
                username=username,
                first_name=first_name,
                is_pro=is_adm,
                pro_expires_at=None,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        else:
            updated = False
            # Если это администратор, гарантируем активный PRO навсегда
            if is_adm and not user.is_pro:
                user.is_pro = True
                user.pro_expires_at = None
                updated = True
            if username and user.username != username:
                user.username = username
                updated = True
            if first_name and user.first_name != first_name:
                user.first_name = first_name
                updated = True
            if updated:
                await session.commit()
                await session.refresh(user)

        return user


async def apply_payment_subscription(
    telegram_id: int,
    plan_id: str,
    duration_days: Optional[int],
    stars_amount: int,
    charge_id: str,
    provider_charge_id: Optional[str] = None,
) -> Tuple[bool, User]:
    """Активирует подписку пользователю при успешной оплате."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalars().first()
        if not user:
            user = User(telegram_id=telegram_id, is_pro=False)
            session.add(user)
            await session.flush()

        # Защита от дублей платежа
        pay_result = await session.execute(
            select(Payment).where(Payment.telegram_payment_charge_id == charge_id)
        )
        existing_payment = pay_result.scalars().first()
        if existing_payment:
            return False, user

        # Рассчитываем срок действия
        now = datetime.now(timezone.utc)
        if duration_days is None:
            # Lifetime
            user.is_pro = True
            user.pro_expires_at = None
        else:
            base_time = now
            if user.is_pro and user.pro_expires_at:
                current_expires = user.pro_expires_at
                if current_expires.tzinfo is None:
                    current_expires = current_expires.replace(tzinfo=timezone.utc)
                if current_expires > now:
                    base_time = current_expires  # Продлеваем текущую подписку
            user.is_pro = True
            user.pro_expires_at = base_time + timedelta(days=duration_days)

        user.stars_spent += stars_amount

        payment = Payment(
            user_id=user.id,
            telegram_payment_charge_id=charge_id,
            provider_payment_charge_id=provider_charge_id,
            plan_id=plan_id,
            stars_amount=stars_amount,
            status="completed",
        )
        session.add(payment)
        await session.commit()
        await session.refresh(user)
        return True, user


async def get_admin_stats() -> dict:
    """Возвращает сводную статистику для админ-панели."""
    async with AsyncSessionLocal() as session:
        users_res = await session.execute(select(User))
        all_users = users_res.scalars().all()

        total_users = len(all_users)
        pro_users = sum(1 for u in all_users if u.check_pro_active())
        total_stars = sum(u.stars_spent for u in all_users)

        payments_res = await session.execute(select(Payment))
        all_payments = payments_res.scalars().all()

        return {
            "total_users": total_users,
            "pro_users": pro_users,
            "total_stars": total_stars,
            "total_payments": len(all_payments),
        }


async def admin_grant_pro(telegram_id: int, duration_days: Optional[int] = None) -> Optional[User]:
    """Выдача PRO пользователю вручную администратором."""
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = res.scalars().first()
        if not user:
            user = User(telegram_id=telegram_id)
            session.add(user)
            await session.flush()

        user.is_pro = True
        if duration_days is None or duration_days <= 0:
            user.pro_expires_at = None  # Навсегда
        else:
            now = datetime.now(timezone.utc)
            user.pro_expires_at = now + timedelta(days=duration_days)

        await session.commit()
        await session.refresh(user)
        return user


async def admin_revoke_pro(telegram_id: int) -> Optional[User]:
    """Отзыв PRO-статуса у пользователя."""
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = res.scalars().first()
        if not user:
            return None

        # Создателя/админа нельзя лишить PRO
        if user.telegram_id in ADMIN_IDS:
            return user

        user.is_pro = False
        user.pro_expires_at = None
        await session.commit()
        await session.refresh(user)
        return user


async def get_all_users() -> list:
    """Получение списка всех пользователей для админки."""
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User).order_by(User.id.desc()))
        return res.scalars().all()


async def get_recent_payments(limit: int = 10) -> list:
    """Получение последних транзакций."""
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Payment).order_by(Payment.id.desc()).limit(limit))
        return res.scalars().all()


async def export_database_json() -> dict:
    """Экспорт всех пользователей и их статусов для резервной копии."""
    async with AsyncSessionLocal() as session:
        users_res = await session.execute(select(User).order_by(User.id.asc()))
        users = users_res.scalars().all()
        return {
            "version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "users_count": len(users),
            "users": [
                {
                    "telegram_id": u.telegram_id,
                    "username": u.username,
                    "first_name": u.first_name,
                    "is_pro": u.is_pro,
                    "pro_expires_at": u.pro_expires_at.isoformat() if u.pro_expires_at else None,
                    "stars_spent": u.stars_spent,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                }
                for u in users
            ]
        }


async def import_database_json(data: dict) -> Tuple[int, int]:
    """Восстановление пользователей из JSON-бэкапа."""
    async with AsyncSessionLocal() as session:
        added = 0
        updated = 0
        raw_users = data.get("users", [])
        for udata in raw_users:
            tid = udata.get("telegram_id")
            if not tid:
                continue
            res = await session.execute(select(User).where(User.telegram_id == int(tid)))
            user = res.scalars().first()

            pro_exp = None
            if udata.get("pro_expires_at"):
                try:
                    pro_exp = datetime.fromisoformat(udata["pro_expires_at"])
                except Exception:
                    pass

            if not user:
                user = User(
                    telegram_id=int(tid),
                    username=udata.get("username"),
                    first_name=udata.get("first_name"),
                    is_pro=bool(udata.get("is_pro", False)) or (int(tid) in ADMIN_IDS),
                    pro_expires_at=pro_exp,
                    stars_spent=int(udata.get("stars_spent", 0)),
                )
                session.add(user)
                added += 1
            else:
                if udata.get("is_pro") and not user.is_pro:
                    user.is_pro = True
                    user.pro_expires_at = pro_exp
                if udata.get("username") and not user.username:
                    user.username = udata.get("username")
                if udata.get("first_name") and not user.first_name:
                    user.first_name = udata.get("first_name")
                user.stars_spent = max(user.stars_spent, int(udata.get("stars_spent", 0)))
                updated += 1

        await session.commit()
        return added, updated
