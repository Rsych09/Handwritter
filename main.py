import asyncio
import os
import sys
import shutil
import threading
import time
import uuid
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional, Dict, Any

import aiofiles

# Настраиваем UTF-8 для консоли Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

# Загружаем переменные окружения из .env
load_dotenv()

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header, Query, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from PIL import Image

from database import (
    init_db,
    get_or_create_user,
    AsyncSessionLocal,
    ADMIN_IDS,
    get_admin_stats,
    admin_grant_pro,
    admin_revoke_pro,
    get_all_users,
)
from auth import validate_telegram_init_data
from bot import bot, dp, PLANS, generate_stars_invoice

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
FONTS_DIR = BASE_DIR / "fonts"
TEMPLATES_DIR = BASE_DIR / "templates"
EXPORTS_DIR = BASE_DIR / "temp_exports"

# Гарантируем наличие необходимых папок
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
FONTS_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_FONT_EXTS = {".ttf", ".otf", ".woff", ".woff2"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация базы данных и фонового поллинга Telegram-бота."""
    print("[INFO] Initializing Handwriter Studio database...")
    await init_db()

    # Очистка старых временных экспортированных файлов (> 1 часа)
    try:
        now_ts = time.time()
        for f in EXPORTS_DIR.glob("*"):
            if f.is_file() and (now_ts - f.stat().st_mtime > 3600):
                f.unlink(missing_ok=True)
    except Exception:
        pass

    polling_task = None
    if bot:
        print("[INFO] Starting Telegram Bot polling in background...")
        polling_task = asyncio.create_task(dp.start_polling(bot))

        # Автоматически обновляем кнопку Menu Button на актуальный WEBAPP_URL
        webapp_url = os.getenv("WEBAPP_URL", "")
        if webapp_url and webapp_url.startswith("https://"):
            try:
                from aiogram.types import MenuButtonWebApp, WebAppInfo
                await bot.set_chat_menu_button(
                    menu_button=MenuButtonWebApp(text="Studio ✍️", web_app=WebAppInfo(url=webapp_url))
                )
                print(f"[INFO] Telegram Menu Button auto-configured: {webapp_url}")
            except Exception as e:
                print(f"[WARN] Could not auto-set chat menu button: {e}")

    yield

    print("[INFO] Shutting down Handwriter Studio...")
    if polling_task:
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
    if bot:
        await bot.session.close()


app = FastAPI(title="Handwriter Studio TMA", lifespan=lifespan)

@app.middleware("http")
async def log_requests_middleware(request: Request, call_next):
    user_agent = request.headers.get("user-agent", "unknown")
    client_ip = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
    print(f"[REQ] {request.method} {request.url.path} from {client_ip} | UA: {user_agent[:60]}")
    response = await call_next(request)
    return response

# Монтируем статические папки для прямого доступа браузера
app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
app.mount("/fonts", StaticFiles(directory=str(FONTS_DIR)), name="fonts")


@app.get("/health")
async def healthcheck():
    """Эндпоинт проверки работоспособности для Render и UptimeRobot."""
    return JSONResponse({"status": "ok", "service": "Handwriter Studio"})


@app.get("/", response_class=HTMLResponse)
async def read_root():
    html_path = TEMPLATES_DIR / "index.html"
    if not html_path.exists():
        return HTMLResponse("<h1>Ошибка: Файл templates/index.html не найден!</h1>", status_code=500)
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/templates")
async def list_templates():
    """Возвращает список всех доступных фонов листов."""
    templates = []
    if ASSETS_DIR.exists():
        for file in sorted(ASSETS_DIR.iterdir()):
            if file.is_file() and file.suffix.lower() in ALLOWED_IMAGE_EXTS:
                width, height = 0, 0
                try:
                    with Image.open(file) as img:
                        width, height = img.size
                except Exception:
                    pass

                if file.name == "template.png":
                    display_name = "Тетрадь в клетку"
                elif file.name == "template_lined.png":
                    display_name = "Тетрадь в линейку"
                elif file.name == "template_blank.png":
                    display_name = "Чистый белый лист"
                else:
                    display_name = file.stem.replace("_", " ").title()

                templates.append({
                    "id": file.name,
                    "filename": file.name,
                    "name": display_name,
                    "url": f"/assets/{file.name}",
                    "width": width,
                    "height": height,
                    "size_bytes": file.stat().st_size,
                    "is_default": (file.name == "template.png"),
                })
    return JSONResponse(templates)


@app.post("/api/upload-template")
async def upload_template(file: UploadFile = File(...)):
    """Загрузка нового фото листа прямо из браузера."""
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимый формат изображения. Поддерживаются: {', '.join(ALLOWED_IMAGE_EXTS)}"
        )

    # Очищаем имя файла и сохраняем
    safe_name = "".join(c for c in Path(file.filename).stem if c.isalnum() or c in ("-", "_")).strip()
    if not safe_name:
        safe_name = "custom_sheet"

    filename = f"{safe_name}{ext}"
    dest_path = ASSETS_DIR / filename

    counter = 1
    while dest_path.exists() and filename != "template.png":
        filename = f"{safe_name}_{counter}{ext}"
        dest_path = ASSETS_DIR / filename
        counter += 1

    try:
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        with Image.open(dest_path) as img:
            width, height = img.size

        return JSONResponse({
            "message": "Фон успешно загружен и сохранён!",
            "id": filename,
            "filename": filename,
            "name": safe_name.replace("_", " ").title(),
            "url": f"/assets/{filename}",
            "width": width,
            "height": height,
            "is_default": False
        })
    except Exception as e:
        if dest_path.exists():
            dest_path.unlink()
        raise HTTPException(status_code=500, detail=f"Ошибка при сохранении файла: {str(e)}")


@app.delete("/api/templates/{filename}")
async def delete_template(filename: str):
    """Удаление пользовательского фона."""
    if filename == "template.png":
        raise HTTPException(status_code=400, detail="Нельзя удалить базовый шаблон по умолчанию")

    file_path = ASSETS_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")

    try:
        file_path.unlink()
        return JSONResponse({"message": f"Шаблон {filename} успешно удален"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Не удалось удалить файл: {str(e)}")


@app.get("/api/fonts")
async def list_fonts():
    """Возвращает список всех доступных шрифтов."""
    fonts = []
    if FONTS_DIR.exists():
        for file in sorted(FONTS_DIR.iterdir()):
            if file.is_file() and file.suffix.lower() in ALLOWED_FONT_EXTS:
                is_default = (file.name == "hand.ttf")
                display_name = "Abram (Рукописный)" if is_default else file.stem.replace("_", " ").title()
                fonts.append({
                    "id": file.name,
                    "filename": file.name,
                    "name": display_name,
                    "url": f"/fonts/{file.name}",
                    "is_default": is_default,
                    "is_pro": not is_default  # Кастомные/дополнительные шрифты доступны по PRO
                })
    return JSONResponse(fonts)


@app.post("/api/upload-font")
async def upload_font(file: UploadFile = File(...)):
    """Загрузка пользовательского шрифта."""
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_FONT_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимый формат шрифта. Поддерживаются: {', '.join(ALLOWED_FONT_EXTS)}"
        )

    safe_name = "".join(c for c in Path(file.filename).stem if c.isalnum() or c in ("-", "_")).strip()
    if not safe_name:
        safe_name = "custom_font"

    filename = f"{safe_name}{ext}"
    dest_path = FONTS_DIR / filename

    counter = 1
    while dest_path.exists() and filename != "hand.ttf":
        filename = f"{safe_name}_{counter}{ext}"
        dest_path = FONTS_DIR / filename
        counter += 1

    try:
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return JSONResponse({
            "message": "Шрифт успешно загружен!",
            "id": filename,
            "filename": filename,
            "name": safe_name.replace("_", " ").title(),
            "url": f"/fonts/{filename}",
            "is_default": False,
            "is_pro": True
        })
    except Exception as e:
        if dest_path.exists():
            dest_path.unlink()
        raise HTTPException(status_code=500, detail=f"Ошибка при сохранении шрифта: {str(e)}")


# ==========================================
# 🌟 TELEGRAM MINI APP & STARS MONETIZATION
# ==========================================

class CreateInvoiceRequest(BaseModel):
    plan_id: str
    init_data: Optional[str] = None


@app.get("/api/plans")
async def get_plans():
    """Возвращает каталог тарифов за Telegram Stars."""
    return JSONResponse(list(PLANS.values()))


@app.get("/api/user-status")
async def get_user_status(
    x_telegram_init_data: Optional[str] = Header(None),
    init_data: Optional[str] = Query(None),
):
    """
    Проверяет статус пользователя по Telegram initData.
    Если запущено в обычном браузере — возвращает статус гостя.
    """
    raw_init_data = x_telegram_init_data or init_data

    if raw_init_data:
        user_info = validate_telegram_init_data(raw_init_data)
        if user_info and "id" in user_info:
            user = await get_or_create_user(
                telegram_id=user_info["id"],
                username=user_info.get("username"),
                first_name=user_info.get("first_name"),
            )
            is_pro = user.check_pro_active()
            is_admin = user.telegram_id in ADMIN_IDS
            return JSONResponse({
                "authenticated": True,
                "user": {
                    "telegram_id": user.telegram_id,
                    "first_name": user.first_name or "Пользователь",
                    "username": user.username,
                    "is_pro": is_pro,
                    "is_admin": is_admin,
                    "pro_expires_at": user.pro_expires_at.isoformat() if user.pro_expires_at else None,
                    "stars_spent": user.stars_spent,
                }
            })

    # Гостевой режим (локальный браузер вне Telegram)
    return JSONResponse({
        "authenticated": False,
        "user": {
            "telegram_id": 0,
            "first_name": "Гость",
            "username": None,
            "is_pro": False,
            "is_admin": False,
            "pro_expires_at": None,
            "stars_spent": 0,
        }
    })


# ==========================================
# 👑 REST API АДМИНИСТРАТОРА
# ==========================================

class AdminGiveProRequest(BaseModel):
    telegram_id: int
    days: Optional[int] = None


class AdminRevokeProRequest(BaseModel):
    telegram_id: int


def verify_admin_request(x_telegram_init_data: Optional[str]) -> int:
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="Требуется авторизация Telegram WebApp.")
    user_info = validate_telegram_init_data(x_telegram_init_data)
    if not user_info or user_info.get("id") not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Доступ разрешен только Создателю / Администратору.")
    return user_info["id"]


@app.get("/api/admin/stats")
async def admin_stats_api(x_telegram_init_data: Optional[str] = Header(None)):
    verify_admin_request(x_telegram_init_data)
    stats = await get_admin_stats()
    return JSONResponse(stats)


@app.get("/api/admin/users")
async def admin_users_api(x_telegram_init_data: Optional[str] = Header(None)):
    verify_admin_request(x_telegram_init_data)
    users = await get_all_users()
    data = []
    for u in users:
        data.append({
            "id": u.id,
            "telegram_id": u.telegram_id,
            "username": u.username,
            "first_name": u.first_name,
            "is_pro": u.check_pro_active(),
            "is_admin": u.telegram_id in ADMIN_IDS,
            "pro_expires_at": u.pro_expires_at.isoformat() if u.pro_expires_at else None,
            "stars_spent": u.stars_spent,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        })
    return JSONResponse(data)


@app.post("/api/admin/give-pro")
async def admin_give_pro_api(
    payload: AdminGiveProRequest,
    x_telegram_init_data: Optional[str] = Header(None),
):
    verify_admin_request(x_telegram_init_data)
    user = await admin_grant_pro(payload.telegram_id, payload.days)
    return JSONResponse({
        "success": True,
        "message": f"PRO успешно выдан пользователю {payload.telegram_id}",
        "user": {
            "telegram_id": user.telegram_id,
            "is_pro": user.is_pro,
            "pro_expires_at": user.pro_expires_at.isoformat() if user.pro_expires_at else None
        }
    })


@app.post("/api/admin/revoke-pro")
async def admin_revoke_pro_api(
    payload: AdminRevokeProRequest,
    x_telegram_init_data: Optional[str] = Header(None),
):
    verify_admin_request(x_telegram_init_data)
    user = await admin_revoke_pro(payload.telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return JSONResponse({
        "success": True,
        "message": f"PRO отозван у пользователя {payload.telegram_id}",
    })


@app.post("/api/create-invoice")
async def create_invoice(
    payload: CreateInvoiceRequest,
    x_telegram_init_data: Optional[str] = Header(None),
):
    """
    Создает ссылку на инвойс в Telegram Stars для открытия в окне Mini App (openInvoice).
    """
    raw_init_data = payload.init_data or x_telegram_init_data
    if not raw_init_data:
        raise HTTPException(
            status_code=401,
            detail="Требуется авторизация Telegram WebApp (initData отсутствует)."
        )

    user_info = validate_telegram_init_data(raw_init_data)
    if not user_info or "id" not in user_info:
        raise HTTPException(
            status_code=403,
            detail="Неверная или устаревшая подпись Telegram initData."
        )

    user_id = user_info["id"]
    plan = PLANS.get(payload.plan_id)
    if not plan:
        raise HTTPException(status_code=400, detail="Тариф не найден.")

    # Генерируем инвойс
    invoice_link = await generate_stars_invoice(user_id=user_id, plan_id=payload.plan_id)
    if not invoice_link:
        raise HTTPException(
            status_code=500,
            detail="Не удалось сгенерировать ссылку на оплату Telegram Stars."
        )

    return JSONResponse({
        "ok": True,
        "invoice_link": invoice_link,
        "plan": plan
    })


@app.post("/api/export_send")
async def export_and_send_to_telegram(
    request: Request,
    file: UploadFile = File(...),
    init_data: Optional[str] = Form(None),
    caption: Optional[str] = Form(None),
    x_telegram_init_data: Optional[str] = Header(None),
):
    """
    Принимает сформированный файл (PDF, ZIP, PNG), сохраняет для прямого скачивания
    и отправляет его напрямую пользователю в личный диалог с Telegram-ботом.
    """
    raw_init_data = init_data or x_telegram_init_data
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Файл пуст.")

    token = uuid.uuid4().hex[:16]
    orig_name = file.filename or "handwritten_document.pdf"
    safe_filename = "".join(c for c in orig_name if c.isalnum() or c in "._-")
    if not safe_filename:
        safe_filename = "handwritten_document.pdf"

    # Сохраняем во временную директорию
    file_path = EXPORTS_DIR / f"{token}_{safe_filename}"
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    # Базовый URL для скачивания
    base_url = os.getenv("WEBAPP_URL", "").rstrip("/")
    if not base_url or not base_url.startswith("http"):
        base_url = str(request.base_url).rstrip("/")

    download_url = f"{base_url}/api/download/{token}/{safe_filename}"

    sent_to_telegram = False
    telegram_error = None

    if raw_init_data and bot:
        user_info = validate_telegram_init_data(raw_init_data)
        if user_info and "id" in user_info:
            user_id = user_info["id"]
            try:
                from aiogram.types import BufferedInputFile
                msg_caption = caption or f"✍️ Ваш файл «{safe_filename}» готов!"
                await bot.send_document(
                    chat_id=user_id,
                    document=BufferedInputFile(content, filename=safe_filename),
                    caption=msg_caption
                )
                sent_to_telegram = True
            except Exception as e:
                telegram_error = str(e)
                print(f"[WARN] Failed to send document to Telegram chat {user_id}: {e}")

    return JSONResponse({
        "ok": True,
        "sent_to_telegram": sent_to_telegram,
        "download_url": download_url,
        "filename": safe_filename,
        "telegram_error": telegram_error
    })


@app.get("/api/download/{token}/{filename}")
async def download_temp_file(token: str, filename: str):
    """
    Прямое скачивание временного файла для Telegram.WebApp.downloadFile и браузеров.
    """
    safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-")
    file_path = EXPORTS_DIR / f"{token}_{safe_filename}"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Срок действия ссылки истек или файл не найден.")

    media_type = "application/octet-stream"
    if safe_filename.endswith(".pdf"):
        media_type = "application/pdf"
    elif safe_filename.endswith(".zip"):
        media_type = "application/zip"
    elif safe_filename.endswith(".png"):
        media_type = "image/png"

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=safe_filename,
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'}
    )


def open_browser(port: int = 8000):
    """Автоматически открывает генератор в браузере по умолчанию при локальном запуске."""
    webbrowser.open(f"http://127.0.0.1:{port}")


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    # Открываем браузер только при локальном запуске на ПК (Windows)
    if not os.getenv("RENDER") and not os.getenv("DYNO") and os.name == "nt":
        threading.Timer(1.5, lambda: open_browser(port)).start()
    uvicorn.run("main:app", host=host, port=port, reload=False)