import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse

app = FastAPI()

# Проверяем структуру папок
os.makedirs("assets", exist_ok=True)
os.makedirs("fonts", exist_ok=True)
os.makedirs("templates", exist_ok=True)

@app.get("/", response_class=HTMLResponse)
async def read_root():
    html_path = os.path.join("templates", "index.html")
    if not os.path.exists(html_path):
        return "<h1>Ошибка: Файл templates/index.html не найден!</h1>"
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()

# Роуты, чтобы фронтенд мог забрать картинку и шрифт напрямую из папок
@app.get("/assets/template.png")
async def get_template():
    if not os.path.exists("assets/template.png"):
        return "Файл assets/template.png не найден", 404
    return FileResponse("assets/template.png")

@app.get("/fonts/hand.ttf")
async def get_font():
    if not os.path.exists("fonts/hand.ttf"):
        return "Файл fonts/hand.ttf не найден", 404
    return FileResponse("fonts/hand.ttf")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)