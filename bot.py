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
from database import get_or_create_user, apply_payment_subscription

logger = logging.getLogger("handwriter_bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
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
            "Экспорт в максимальном качестве",
            "Приоритетная генерация",
            "Личный кабинет и облачное сохранение",
        ],
    },
}

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()


def get_webapp_keyboard() -> InlineKeyboardMarkup:
    """Генерирует клавиатуру с кнопкой открытия Mini App."""
    current_url = os.getenv("WEBAPP_URL", WEBAPP_URL)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✍️ Открыть Handwriter Studio",
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
    )


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

    text = (
        f"👋 **Привет, {user.first_name if user else 'друг'}!**\n\n"
        "Добро пожаловать в **Handwriter Studio** — профессиональный генератор рукописных конспектов и лекций.\n\n"
        "✨ **Что умеет студия:**\n"
        "• Превращает любой печатный текст в реалистичный рукописный почерк;\n"
        "• Движок «Живой руки»: дрожание строк, разный наклон букв и нажим чернил;\n"
        "• Развороты тетрадей в клетку, линейку или загрузка фото своей тетради;\n"
        "• Моментальный экспорт в чистый многостраничный **PDF** или **ZIP**.\n\n"
        "👇 Нажмите кнопку ниже, чтобы запустить приложение прямо в Telegram:"
    )

    await message.answer(text, parse_mode="Markdown", reply_markup=get_webapp_keyboard())


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
