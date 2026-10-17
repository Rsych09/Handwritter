# ✒️ Handwriter Studio — Telegram Mini App & Bot ⭐️

> Профессиональный веб-генератор рукописных конспектов и лекций для Telegram Mini App с монетизацией через **Telegram Stars (Звёзды)**.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688?style=flat-square)
![aiogram](https://img.shields.io/badge/aiogram-3.3%2B-2CA5E0?style=flat-square)
![Telegram Stars](https://img.shields.io/badge/Telegram-Stars%20(XTR)-F59E0B?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-zinc?style=flat-square)

---

## ✨ Возможности и функционал

- 📱 **Telegram Mini App (TMA)**:
  - Бесшовная авторизация пользователей через криптографическую валидацию `initData` (HMAC-SHA256);
  - Адаптивный мобильный интерфейс с нативной нижней навигацией и поддержкой Telegram SDK;
  - Тактильный отклик (*Telegram Haptic Feedback*);
  - Интеграция с ботом: команда `/start`, `/pro`, быстрый запуск приложения по кнопке.
- ⭐️ **Монетизация через Telegram Stars (`XTR`)**:
  - Встроенный каталог тарифов («1 день PRO», «1 месяц PRO», «Навсегда Lifetime VIP»);
  - Нативное всплывающее окно оплаты инвойса прямо внутри Telegram Mini App (`Telegram.WebApp.openInvoice`);
  - Автоматическая обработка платежей через `pre_checkout_query` и `successful_payment`;
  - Сохранение истории транзакций и статуса подписки в базе данных SQLite.
- ✍️ **Движок «Живой руки» (Human Realism Engine)**:
  - Вертикальное дрожание строки (*Baseline Jitter*);
  - Микронаклон отдельных букв (*Slant Jitter*);
  - Случайный размер символов и нажим пера (*Ink Flow*);
  - Настраиваемые поля, переплет тетради и абзацный отступ.
- 📄 **Экспорт и ограничения Free/PRO**:
  - Экспорт в многостраничный **PDF** и **ZIP**-архив;
  - В бесплатной версии: аккуратный водяной знак со ссылкой на бота и лимит экспорта до 3 страниц;
  - В PRO-версии: чистый экспорт без водяных знаков и безлимитная генерация страниц.

---

## 📁 Структура проекта

```text
├── assets/            # Шаблоны тетрадных листов (клетка, линейка, чистый лист)
├── fonts/             # Рукописные шрифты (.ttf, .otf)
├── templates/         # Веб-интерфейс (HTML5 Canvas, Tailwind CSS, Lucide, Telegram WebApp SDK)
├── auth.py            # Валидация подписи Telegram initData (HMAC-SHA256)
├── bot.py             # Telegram-бот на aiogram 3 (команды, обработчик Stars платежей)
├── database.py        # База данных SQLite (SQLAlchemy + aiosqlite): пользователи, подписки, платежи
├── main.py            # FastAPI бэкенд с REST API и одновременным фоновым поллингом бота
├── requirements.txt   # Зависимости Python
├── .env               # Токен бота и настройки окружения
├── run_server.bat     # Скрипт запуска для Windows
└── generator.vbs      # Скрытый фоновый запуск
```

---

## 🚀 Быстрый старт и запуск

### 1. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 2. Настройка `.env`
Файл `.env` уже создан в корне проекта:
```env
BOT_TOKEN=8961172401:AAF-q6J_EbbbmX2VTrxCRA1e9rzj_tHQJ6M
DATABASE_URL=sqlite+aiosqlite:///./handwriter.db
WEBAPP_URL=https://t.me/HandwriterStudio_bot/app
HOST=127.0.0.1
PORT=8000
```

### 3. Запуск сервера и бота
```bash
python main.py
```
> При запуске FastAPI поднимет локальный сервер на порту 8000, автоматически инициализирует базу данных SQLite и параллельно запустит Telegram-бота в фоновом режиме!

---

## 🌐 Как открыть приложение внутри Telegram

Telegram Mini App требует HTTPS:

1. **Для локального тестирования (через туннель)**:
   - Скачайте `cloudflared` или `ngrok`:
     ```bash
     ngrok http 8000
     ```
   - Скопируйте полученную ссылку `https://xxxx.ngrok-free.app`.
   - В `@BotFather` настройте эту ссылку для команды `/newapp` или `/setmenubutton`.

2. **Для боевого продакшена**:
   - Разверните проект на VPS (например, Timeweb, Selectel, Hetzner);
   - Настройте домен с SSL-сертификатом (Let's Encrypt / Certbot);
   - Укажите HTTPS-адрес вашего сервера в `@BotFather`.
