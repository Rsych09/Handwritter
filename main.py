import os
import shutil
import threading
import webbrowser
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

app = FastAPI(title="Handwriter Studio")

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
FONTS_DIR = BASE_DIR / "fonts"
TEMPLATES_DIR = BASE_DIR / "templates"

# Гарантируем наличие необходимых папок
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
FONTS_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

# Монтируем статические папки для прямого доступа браузера
app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
app.mount("/fonts", StaticFiles(directory=str(FONTS_DIR)), name="fonts")

ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_FONT_EXTS = {".ttf", ".otf", ".woff", ".woff2"}

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
                    "is_default": (file.name == "template.png")
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
    
    # Если файл с таким именем уже есть и это не template.png, добавим индекс
    counter = 1
    while dest_path.exists() and filename != "template.png":
        filename = f"{safe_name}_{counter}{ext}"
        dest_path = ASSETS_DIR / filename
        counter += 1

    try:
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Получаем размеры загруженного изображения
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
                    "is_default": is_default
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
            "is_default": False
        })
    except Exception as e:
        if dest_path.exists():
            dest_path.unlink()
        raise HTTPException(status_code=500, detail=f"Ошибка при сохранении шрифта: {str(e)}")

def open_browser():
    """Автоматически открывает генератор в браузере по умолчанию при запуске."""
    webbrowser.open("http://127.0.0.1:8000")

if __name__ == "__main__":
    import uvicorn
    threading.Timer(1.5, open_browser).start()
    uvicorn.run(app, host="127.0.0.1", port=8000)