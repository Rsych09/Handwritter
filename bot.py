import logging
import os
from typing import Dict, Any, Optional
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    PreCheckoutQuery,
    LabeledPrice,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
)
from database import (
    get_or_create_user,
    apply_payment_subscription,
    ADMIN_IDS,
    get_admin_stats,
    admin_grant_pro,
    admin_revoke_pro,
    get_all_users,
    get_recent_payments,
)

logger = logging.getLogger("handwriter_bot")

DEFAULT_BOT_TOKEN = "8961172401:AAF-q6J_EbbbmX2VTrxCRA1e9rzj_tHQJ6M"
BOT_TOKEN = os.getenv("BOT_TOKEN", DEFAULT_BOT_TOKEN)
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://t.me/HandwriterStudio_bot/app")

# Каталог тарифов за Telegram Stars (валюта XTR)
PLANS: Dict[str, Dict[str, Any]] = {
    "plan_day": {
        "id": "plan_day",
        "name": "1 день PRO (Срочный реферат)",
        "badge": "⚡ Быстрый старт",
        "description": "24 часа полного безлимита без водяных знаков, экспорт в PDF/ZIP и все шрифты.",
        "stars": 15,
        "duration_days": 1,
        "features": [
            "Без водяного знака",
            "Все рукописные шрифты",
            "🕶️ Режим «Анти-палево» (названия как с камеры)",
            "Экспорт многостраничных PDF",
            "Доступ на 24 часа",
        ],
    },
    "plan_month": {
        "id": "plan_month",
        "name": "1 месяц PRO (Студент)",
        "badge": "🔥 Выбор большинства",
        "description": "30 дней безлимитной генерации конспектов, все премиум стили и чернила.",
        "stars": 75,
        "duration_days": 30,
        "is_popular": True,
        "features": [
            "Без водяного знака",
            "Все рукописные шрифты",
            "🕶️ Режим «Анти-палево» (названия как с камеры)",
            "Ultra HD качество (300 DPI)",
            "Неограниченно страниц конспектов",
            "Загрузка своих фонов тетрадей",
            "Доступ на 30 дней",
        ],
    },
    "plan_forever": {
        "id": "plan_forever",
        "name": "Навсегда (VIP Lifetime)",
        "badge": "👑 Безлимит навсегда",
        "description": "Вечный доступ ко всем текущим и будущим обновлениям, шрифтам и функциям.",
        "stars": 250,
        "duration_days": None,
        "features": [
            "Вечный доступ без ограничений",
            "Все текущие и будущие шрифты",
            "🕶️ Режим «Анти-палево» (названия как с камеры)",
            "Экспорт в максимальном качестве",
            "Приоритетная генерация",
            "Личный кабинет и облачное сохранение",
        ],
    },
}

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()


def get_webapp_keyboard(user_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру с кнопкой открытия Mini App и админки для создателя."""
    current_url = os.getenv("WEBAPP_URL", WEBAPP_URL)
    buttons = [
        [
            InlineKeyboardButton(
                text="✍️ Открыть Studio (PRO ✨)" if user_id in ADMIN_IDS else "✍️ Открыть Handwriter Studio",
                web_app=WebAppInfo(url=current_url),
            )
        ],
        [
            InlineKeyboardButton(
                text="⭐ PRO Тарифы",
                callback_data="show_plans",
            )
        ]
    ]
    if user_id in ADMIN_IDS:
        buttons.append([
            InlineKeyboardButton(
                text="👑 Панель Создателя",
                callback_data="admin_dashboard",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.message(CommandStart())
async def handle_start(message: Message):
    """Обработчик команды /start."""
    user = message.from_user
    if user:
        await get_or_create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
        )

    is_admin = user and user.id in ADMIN_IDS

    admin_badge = "\n\n👑 **Вы авторизованы как Создатель проекта!** У вас пожизненный полный PRO-доступ без ограничений." if is_admin else ""

    text = (
        f"👋 **Привет, {user.first_name if user else 'друг'}!**\n\n"
        "Добро пожаловать в **Handwriter Studio** — профессиональный генератор рукописных конспектов и лекций.\n\n"
        "✨ **Что умеет студия:**\n"
        "• Превращает любой печатный текст в реалистичный рукописный почерк;\n"
        "• Движок «Живой руки»: дрожание строк, разный наклон букв и нажим чернил;\n"
        "• Развороты тетрадей в клетку, линейку или загрузка фото своей тетради;\n"
        "• Моментальный экспорт в чистый многостраничный **PDF** или **ZIP**."
        f"{admin_badge}\n\n"
        "👇 Нажмите кнопку ниже, чтобы запустить приложение прямо в Telegram:"
    )

    await message.answer(text, parse_mode="Markdown", reply_markup=get_webapp_keyboard(user.id if user else None))


@dp.message(Command("pro"))
async def handle_pro(message: Message):
    """Обработчик команды /pro для просмотра тарифов."""
    text = (
        "💎 **Премиум возможности Handwriter Studio PRO**\n\n"
        "Откройте приложение и перейдите во вкладку **«Тарифы ⭐»**, чтобы оплатить любой тариф прямо через **Telegram Stars**:\n\n"
    )
    for p in PLANS.values():
        badge = f" [{p.get('badge')}]" if p.get("badge") else ""
        text += f"⭐ **{p['name']}**{badge} — `{p['stars']} Stars`\n_{p['description']}_\n\n"

    await message.answer(text, parse_mode="Markdown", reply_markup=get_webapp_keyboard())


@dp.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    """
    Обязательное подтверждение заказа от Telegram.
    Telegram ожидает ответ в течение 10 секунд.
    """
    payload = pre_checkout_query.invoice_payload
    # payload имеет формат "user_id:plan_id"
    parts = payload.split(":", 1)
    plan_id = parts[1] if len(parts) > 1 else parts[0]

    if plan_id in PLANS:
        await pre_checkout_query.answer(ok=True)
    else:
        await pre_checkout_query.answer(ok=False, error_message="Выбранный тариф не найден или устарел.")


@dp.message(F.successful_payment)
async def process_successful_payment(message: Message):
    """Обработка успешной оплаты Telegram Stars."""
    sp = message.successful_payment
    user_id = message.from_user.id
    payload = sp.invoice_payload
    parts = payload.split(":", 1)
    plan_id = parts[1] if len(parts) > 1 else parts[0]

    plan = PLANS.get(plan_id)
    plan_name = plan["name"] if plan else "PRO Тариф"
    duration_days = plan.get("duration_days") if plan else None

    # Применяем подписку в БД
    success, user = await apply_payment_subscription(
        telegram_id=user_id,
        plan_id=plan_id,
        duration_days=duration_days,
        stars_amount=sp.total_amount,
        charge_id=sp.telegram_payment_charge_id,
        provider_charge_id=sp.provider_payment_charge_id,
    )

    congrats_text = (
        "🎉 **Оплата прошла успешно!**\n\n"
        f"⭐ Списано звёзд: **{sp.total_amount} XTR**\n"
        f"🔓 Тариф **{plan_name}** успешно активирован!\n\n"
        "**Теперь вам доступно:**\n"
        "✅ Генерация без водяных знаков;\n"
        "✅ Все премиум-почерки и стили чернил;\n"
        "✅ Многостраничный экспорт в высоком качестве.\n\n"
        "Запустите Handwriter Studio прямо сейчас:"
    )

    await message.answer(congrats_text, parse_mode="Markdown", reply_markup=get_webapp_keyboard())


async def generate_stars_invoice(user_id: int, plan_id: str) -> Optional[str]:
    """Генерирует ссылку на оплату инвойса в Telegram Stars."""
    if not bot:
        return None
    plan = PLANS.get(plan_id)
    if not plan:
        return None

    try:
        link = await bot.create_invoice_link(
            title=plan["name"],
            description=plan["description"],
            payload=f"{user_id}:{plan_id}",
            currency="XTR",  # Telegram Stars
            prices=[LabeledPrice(label=plan["name"], amount=plan["stars"])],
        )
        return link
    except Exception as e:
        logger.error(f"Error creating invoice link: {e}")
        return None


# ==========================================
# 👑 АДМИН-ПАНЕЛЬ И КОМАНДЫ СОЗДАТЕЛЯ
# ==========================================

async def build_admin_text_and_keyboard():
    stats = await get_admin_stats()
    text = (
        "👑 **Панель Управления Handwriter Studio**\n\n"
        f"👥 Всего зарегистрировано пользователей: **{stats['total_users']}**\n"
        f"⭐ Активных PRO-пользователей: **{stats['pro_users']}**\n"
        f"💰 Всего заработано звёзд: **{stats['total_stars']} Stars**\n"
        f"🧾 Успешных оплат: **{stats['total_payments']}**\n\n"
        "🛠 **Быстрые команды администратора:**\n"
        "• `/givepro <tg_id> [дней]` — выдать PRO (без дней или 0 = навсегда)\n"
        "• `/revokepro <tg_id>` — забрать PRO\n"
        "• `/broadcast <текст>` — сделать объявление/рассылку всем\n"
        "• `/users` — посмотреть последних пользователей"
    )
    current_url = os.getenv("WEBAPP_URL", WEBAPP_URL)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Обновить статистику", callback_data="admin_refresh"),
            InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users"),
        ],
        [
            InlineKeyboardButton(text="✍️ Запустить Studio (PRO)", web_app=WebAppInfo(url=current_url)),
        ]
    ])
    return text, kb


@dp.message(Command("admin"))
async def handle_admin_command(message: Message):
    """Команда /admin для входа в панель управления."""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет доступа к панели администратора.")
        return
    text, kb = await build_admin_text_and_keyboard()
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


@dp.callback_query(F.data.in_({"admin_dashboard", "admin_refresh"}))
async def handle_admin_dashboard_callback(callback_query):
    if callback_query.from_user.id not in ADMIN_IDS:
        await callback_query.answer("⛔ Доступ запрещен.", show_alert=True)
        return
    text, kb = await build_admin_text_and_keyboard()
    try:
        await callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        pass
    await callback_query.answer("Статистика обновлена!")


@dp.callback_query(F.data == "admin_users")
@dp.message(Command("users"))
async def handle_admin_users(event):
    user_id = event.from_user.id
    if user_id not in ADMIN_IDS:
        if isinstance(event, Message):
            await event.answer("⛔ Доступ запрещен.")
        else:
            await event.answer("⛔ Доступ запрещен.", show_alert=True)
        return

    users = await get_all_users()
    lines = ["👥 **Список пользователей (последние 20):**\n"]
    for u in users[:20]:
        status = "👑 Создатель" if u.telegram_id in ADMIN_IDS else ("⭐ PRO" if u.check_pro_active() else "Свободный")
        u_name = f"@{u.username}" if u.username else (u.first_name or "Без имени")
        lines.append(f"• `{u.telegram_id}` | {u_name} — **{status}**")

    out_text = "\n".join(lines)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin_dashboard")]
    ])
    if isinstance(event, Message):
        await event.answer(out_text, parse_mode="Markdown", reply_markup=kb)
    else:
        try:
            await event.message.edit_text(out_text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            pass
        await event.answer()


@dp.message(Command("givepro"))
async def handle_give_pro(message: Message):
    """Выдача PRO: /givepro <tg_id> [дней]"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Доступ запрещен.")
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer("⚠️ Использование: `/givepro <telegram_id> [дней]`\nНапример: `/givepro 123456789 30` или `/givepro 123456789` (навсегда)", parse_mode="Markdown")
        return

    try:
        target_id = int(parts[1])
        days = int(parts[2]) if len(parts) > 2 else None
    except ValueError:
        await message.answer("❌ Ошибка: ID и дни должны быть числами.")
        return

    user = await admin_grant_pro(target_id, days)
    dur_str = f"на {days} дней" if days else "НАВСЕГДА"
    await message.answer(f"✅ Успешно! Пользователю `{target_id}` выдан PRO **{dur_str}**.", parse_mode="Markdown")


@dp.message(Command("revokepro"))
async def handle_revoke_pro(message: Message):
    """Отзыв PRO: /revokepro <tg_id>"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Доступ запрещен.")
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer("⚠️ Использование: `/revokepro <telegram_id>`", parse_mode="Markdown")
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("❌ Ошибка: ID должен быть числом.")
        return

    if target_id in ADMIN_IDS:
        await message.answer("⚠️ Нельзя отозвать PRO у Создателя проекта.")
        return

    user = await admin_revoke_pro(target_id)
    if not user:
        await message.answer("❌ Пользователь не найден в базе.")
        return

    await message.answer(f"✅ PRO-статус у пользователя `{target_id}` отозван.", parse_mode="Markdown")


@dp.message(Command("broadcast"))
async def handle_broadcast(message: Message):
    """Рассылка сообщения всем пользователям: /broadcast <текст>"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Доступ запрещен.")
        return

    text_to_send = message.text.replace("/broadcast", "", 1).strip()
    if not text_to_send:
        await message.answer("⚠️ Использование: `/broadcast Ваше сообщение здесь`", parse_mode="Markdown")
        return

    users = await get_all_users()
    sent = 0
    failed = 0
    status_msg = await message.answer(f"⏳ Начинаю рассылку для {len(users)} пользователей...")

    for u in users:
        try:
            await bot.send_message(u.telegram_id, text_to_send, parse_mode="Markdown")
            sent += 1
            await asyncio.sleep(0.05)  # Защита от лимитов Telegram
        except Exception:
            failed += 1

    await status_msg.edit_text(f"📢 **Рассылка завершена!**\n\n✅ Успешно доставлено: {sent}\n❌ Ошибок / заблокировали бота: {failed}", parse_mode="Markdown")
