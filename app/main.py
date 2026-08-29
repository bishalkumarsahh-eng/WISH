import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from .db import db, setup_indexes
from .bot import start_bot_background
from .config import BASE_URL

@asynccontextmanager
async def lifespan(app: FastAPI):
    await setup_indexes()
    start_bot_background()
    yield

app = FastAPI(title="WishVerse", lifespan=lifespan)

@app.get("/", response_class=HTMLResponse)
async def home():
    return HTMLResponse("""
    <html><head><title>WishVerse</title></head>
    <body style='font-family:Arial;background:#111;color:white;text-align:center;padding:80px'>
    <h1>✨ WishVerse</h1><p>Create beautiful surprise websites through Telegram.</p>
    </body></html>
    """)

@app.get("/health")
async def health():
    return {"ok": True}

@app.get("/s/{slug}", response_class=HTMLResponse)
async def website(slug: str):
    if db is None:
        raise HTTPException(503, "Database not configured")
    site = await db.websites.find_one({"slug": slug})
    if not site or not site.get("published"):
        raise HTTPException(404, "Website not found or not published")
    title = site.get("title", "A Special Surprise")
    message = site.get("message", "")
    bg = site.get("background", "gradient")
    effect = {
        "hearts": "💖 ❤️ 💕 💗 💓",
        "flowers": "🌸 🌷 🌺 🌸",
        "balloons": "🎈 🎈 🎈 🎈",
        "stars": "✨ ⭐ ✨ 🌟"
    }.get(bg, "")
    return HTMLResponse(f"""
<!doctype html>
<html>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{title}</title>
<style>
*{{box-sizing:border-box}} body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
font-family:Arial,sans-serif;color:white;background:linear-gradient(135deg,#6a11cb,#2575fc);overflow:hidden}}
.card{{width:min(900px,90vw);padding:50px 28px;border:1px solid rgba(255,255,255,.3);border-radius:30px;
background:rgba(255,255,255,.12);backdrop-filter:blur(14px);text-align:center;box-shadow:0 20px 80px rgba(0,0,0,.35)}}
h1{{font-size:clamp(2rem,7vw,5rem);margin:0 0 25px}}p{{font-size:clamp(1.1rem,2.5vw,1.5rem);line-height:1.8;white-space:pre-wrap}}
.fx{{position:fixed;inset:0;pointer-events:none;font-size:40px;word-spacing:35px;opacity:.35;animation:float 8s linear infinite}}
@keyframes float{{0%{{transform:translateY(100vh)}}100%{{transform:translateY(-110vh)}}}}
</style>
</head>
<body>
<div class='fx'>{effect}</div>
<main class='card'><h1>{title}</h1><p>{message}</p><div>✨ Made with WishVerse ✨</div></main>
</body></html>
""")
