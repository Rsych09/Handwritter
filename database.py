import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
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

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./handwriter.db")

engine = create_async_engine(DATABASE_URL, echo=False)
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
        """Проверяет, активен ли PRO-статус."""
        if not self.is_pro:
            return False
        # Если дата окончания не установлена (None) — это вечная подписка (Lifetime)
        if self.pro_expires_at is None:
            return True
        now = datetime.now(timezone.utc)
        # Если время с таймзоной или без, нормализуем
        expires = self.pro_expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires > now


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
    """Создание таблиц при старте сервера."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_or_create_user(
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
) -> User:
    """Получить или зарегистрировать пользователя."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalars().first()

        if not user:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                is_pro=False,
                pro_expires_at=None,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        else:
            # Обновим имя / username если изменились
            updated = False
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
