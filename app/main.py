from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from html import escape
from .db import db, setup_indexes

@asynccontextmanager
async def lifespan(app: FastAPI):
    await setup_indexes()
    yield

app = FastAPI(title="WishVerse", lifespan=lifespan)

@app.get("/")
async def home():
    return {"status": "WishVerse web server running"}

@app.get("/health")
async def health():
    return {"ok": True}

@app.get("/s/{slug}", response_class=HTMLResponse)
async def website(slug: str):
    if db is None:
        raise HTTPException(503, "Database not configured")
    site = await db.websites.find_one({"slug": slug, "published": True})
    if not site:
        raise HTTPException(404, "Website not found")
    title = escape(site.get("title", "A Special Surprise"))
    message = escape(site.get("message", ""))
    bg = site.get("background", "gradient")
    effects = {"hearts":"💖 ❤️ 💕 💗", "flowers":"🌸 🌷 🌺", "balloons":"🎈 🎈 🎈", "stars":"✨ ⭐ 🌟"}
    fx = effects.get(bg, "")
    return HTMLResponse(f'''<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;font-family:Arial,sans-serif;color:#fff;background:linear-gradient(135deg,#6a11cb,#2575fc);overflow:hidden}}
.card{{width:min(900px,90vw);padding:45px 25px;text-align:center;border-radius:28px;background:rgba(255,255,255,.12);backdrop-filter:blur(14px)}}
h1{{font-size:clamp(2rem,7vw,5rem)}}p{{white-space:pre-wrap;font-size:1.25rem;line-height:1.8}}
.fx{{position:fixed;inset:0;pointer-events:none;font-size:38px;opacity:.35;animation:move 8s linear infinite}}
@keyframes move{{from{{transform:translateY(100vh)}}to{{transform:translateY(-110vh)}}}}
</style></head><body><div class="fx">{fx}</div><main class="card"><h1>{title}</h1><p>{message}</p><div>✨ Made with WishVerse ✨</div></main></body></html>''')
