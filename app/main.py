from contextlib import asynccontextmanager
from html import escape
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
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

@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)

def render_site(site):
    title = escape(site.get("title", "A Special Surprise"))
    message = escape(site.get("message", ""))
    bg = site.get("background", "gradient")
    effects = {
        "hearts": "💖 ❤️ 💕 💗 💓 💖 ❤️ 💕",
        "flowers": "🌸 🌷 🌺 🌸 🌷 🌺",
        "balloons": "🎈 🎈 🎈 🎈 🎈",
        "stars": "✨ ⭐ 🌟 ✨ ⭐ 🌟"
    }
    fx = effects.get(bg, "")
    return HTMLResponse(f'''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;min-height:100vh;display:grid;place-items:center;font-family:Arial,sans-serif;color:#fff;background:linear-gradient(135deg,#6a11cb,#2575fc);overflow:hidden}}
.card{{width:min(900px,90vw);padding:50px 28px;text-align:center;border:1px solid rgba(255,255,255,.3);border-radius:30px;background:rgba(255,255,255,.12);backdrop-filter:blur(14px);box-shadow:0 20px 80px rgba(0,0,0,.35)}}
h1{{font-size:clamp(2rem,7vw,5rem);margin:0 0 25px}}
p{{white-space:pre-wrap;font-size:clamp(1.05rem,2.5vw,1.45rem);line-height:1.8}}
.fx{{position:fixed;inset:0;pointer-events:none;font-size:38px;word-spacing:25px;opacity:.35;animation:move 8s linear infinite}}
@keyframes move{{from{{transform:translateY(100vh)}}to{{transform:translateY(-110vh)}}}}
.badge{{margin-top:30px;opacity:.7;font-size:.9rem}}
</style>
</head>
<body>
<div class="fx">{fx}</div>
<main class="card">
<h1>{title}</h1>
<p>{message}</p>
<div class="badge">✨ Made with WishVerse ✨</div>
</main>
</body>
</html>''')

@app.get("/s/{slug}", response_class=HTMLResponse)
async def public_website(slug: str):
    if db is None:
        raise HTTPException(503, "Database not configured")
    site = await db.websites.find_one({"slug": slug, "published": True})
    if not site:
        raise HTTPException(404, "Website not found or not published")
    return render_site(site)

@app.get("/preview/{slug}", response_class=HTMLResponse)
async def preview_website(slug: str, token: str):
    if db is None:
        raise HTTPException(503, "Database not configured")
    site = await db.websites.find_one({"slug": slug, "preview_token": token})
    if not site:
        raise HTTPException(404, "Invalid preview link")
    return render_site(site)
