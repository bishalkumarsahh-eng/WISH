from contextlib import asynccontextmanager
from datetime import datetime, timezone
from html import escape
from urllib.parse import quote
import httpx

from fastapi import FastAPI, HTTPException, Response, Query
from fastapi.responses import HTMLResponse
from .config import BOT_TOKEN
from .db import db, setup_indexes
from .themes import THEMES, PREMIUM_THEME_CONFIG

FONT_MAP = {
    "inter": ("Inter", "Inter:wght@400;600;700;800"),
    "playfair": ("Playfair Display", "Playfair+Display:wght@400;600;700"),
    "merriweather": ("Merriweather", "Merriweather:wght@400;700"),
    "poppins": ("Poppins", "Poppins:wght@400;600;700"),
    "dancing": ("Dancing Script", "Dancing+Script:wght@400;600;700"),
    "great_vibes": ("Great Vibes", "Great+Vibes"),
    "cinzel": ("Cinzel", "Cinzel:wght@400;600;700"),
    "cormorant": ("Cormorant Garamond", "Cormorant+Garamond:wght@400;500;600;700"),
    "montserrat": ("Montserrat", "Montserrat:wght@400;600;700;800"),
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    await setup_indexes()
    yield

app = FastAPI(title="WishVerse", lifespan=lifespan)

@app.get("/")
async def home():
    return {"status": "WishVerse web server running", "version": "professional-media-fonts"}

@app.get("/health")
async def health():
    return {"ok": True}

@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)

def as_utc(value):
    if value is None:
        return None
    # Defensive support for websites created by older deployments where
    # MongoDB datetimes may be returned without tzinfo.
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

def is_preview_valid(site, token):
    if not token or site.get("preview_token") != token:
        return False
    expires = as_utc(site.get("preview_expires_at"))
    return bool(expires and expires > datetime.now(timezone.utc))

async def get_media_bytes(file_id):
    if not BOT_TOKEN:
        raise HTTPException(503, "Media service unavailable")
    async with httpx.AsyncClient(timeout=45.0) as client:
        info = await client.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getFile", params={"file_id": file_id})
        info.raise_for_status()
        data = info.json()
        if not data.get("ok"):
            raise HTTPException(404, "Media not found")
        path = data["result"]["file_path"]
        media = await client.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{path}")
        media.raise_for_status()
        return media.content, media.headers.get("content-type", "application/octet-stream")

async def authorized_site(slug, token=None):
    site = await db.websites.find_one({"slug": slug})
    if not site:
        raise HTTPException(404, "Website not found")

    if token:
        if not is_preview_valid(site, token):
            raise HTTPException(403, "Invalid or expired preview")
        return site

    if not site.get("published"):
        raise HTTPException(404, "Website not published")
    if not site.get("is_permanent"):
        expires = as_utc(site.get("published_expires_at"))
        now = datetime.now(timezone.utc)
        if not expires or expires <= now:
            await db.websites.update_one({"_id": site["_id"]}, {"$set": {"published": False, "expired_at": now}})
            raise HTTPException(410, "This website has expired")
    return site

@app.get("/media/{slug}/photo/{index}")
async def site_photo(slug: str, index: int, token: str | None = Query(default=None)):
    site = await authorized_site(slug, token)
    photos = site.get("photo_file_ids", [])
    if index < 0 or index >= len(photos):
        raise HTTPException(404, "Photo not found")
    content, content_type = await get_media_bytes(photos[index])
    return Response(content=content, media_type=content_type, headers={"Cache-Control": "public, max-age=3600"})

@app.get("/media/{slug}/video")
async def site_video(slug: str, token: str | None = Query(default=None)):
    site = await authorized_site(slug, token)
    file_id = site.get("video_file_id")
    if not file_id:
        raise HTTPException(404, "Video not found")
    content, content_type = await get_media_bytes(file_id)
    return Response(content=content, media_type=content_type, headers={"Cache-Control": "public, max-age=3600"})

def render_premium_story(site, preview=False, preview_token=None):
    import json
    cfg = PREMIUM_THEME_CONFIG.get(site.get("premium_theme") or site.get("theme"), PREMIUM_THEME_CONFIG["custom_cinematic"])
    scene = cfg.get("scene", "shooting_stars")
    title = escape(site.get("title", "A Special Surprise"))
    message = escape(site.get("message", ""))
    name = escape(site.get("recipient_name", "")) or "you"
    category = escape(site.get("type", "special"))
    token_q = f"?token={quote(preview_token)}" if preview and preview_token else ""
    photos = site.get("photo_file_ids", [])
    photo_cards = "".join(
        f"<div class='photo'><img src='/media/{site['slug']}/photo/{i}{token_q}' loading='lazy'></div>"
        for i in range(len(photos))
    ) or "<div class='empty'>✨ Your memories will appear here</div>"
    video = (f"<video controls playsinline src='/media/{site['slug']}/video{token_q}'></video>"
             if site.get("video_file_id") else "<div class='empty'>🎬 No video was added to this story</div>")
    html = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title><link href="https://fonts.googleapis.com/css2?family=Dancing+Script:wght@500;700&family=DM+Sans:wght@400;700;800&family=Nunito:wght@700;800;900&display=swap" rel="stylesheet"><style>
:root{--accent:__ACCENT__;--bg:__BG__}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:#fff;font-family:'DM Sans',sans-serif;overflow-x:hidden}.preview{position:fixed;top:0;left:0;right:0;z-index:99;background:#111d;padding:10px;text-align:center;font-weight:800;font-size:12px}.confetti{position:fixed;inset:0;pointer-events:none;z-index:0;background-image:radial-gradient(circle,#fff 1px,transparent 1.5px),radial-gradient(circle,var(--accent) 1px,transparent 2px);background-size:52px 52px,87px 87px;opacity:.45;animation:drift 16s linear infinite}@keyframes drift{to{transform:translate(50px,100px)}}main{position:relative;z-index:1}.screen{display:none;min-height:100svh;padding:76px 20px 42px;align-items:center;justify-content:center;text-align:center}.screen.active{display:flex;flex-direction:column}.eyebrow{text-transform:uppercase;letter-spacing:.16em;font-size:11px;opacity:.72}.emoji{font-size:clamp(64px,13vw,130px);filter:drop-shadow(0 12px 30px #0007);animation:bob 3s ease-in-out infinite}@keyframes bob{50%{transform:translateY(-12px) rotate(4deg)}}h1,h2{font-family:'Nunito',sans-serif;margin:12px 0;line-height:1.02}h1{font-size:clamp(42px,10vw,90px)}h2{font-size:clamp(30px,7vw,58px)}em{color:var(--accent);font-family:'Dancing Script',cursive;font-size:1.25em}.lead,.copy{max-width:700px;line-height:1.8;font-size:clamp(16px,2.5vw,20px);white-space:pre-wrap}.btn,.option{border:0;border-radius:999px;padding:16px 25px;margin:8px;font:800 16px 'DM Sans';cursor:pointer;background:#fff;color:#17111b;box-shadow:0 14px 35px #0005;transition:.25s}.btn:hover,.option:hover{transform:translateY(-4px) scale(1.03)}.option{background:#ffffff18;color:#fff;border:1px solid #ffffff30}.choice{display:flex;flex-wrap:wrap;justify-content:center;max-width:700px}.progress{height:5px;width:min(500px,80vw);background:#ffffff22;border-radius:9px;margin:14px}.progress span{display:block;height:100%;width:50%;background:var(--accent);border-radius:9px}.gift{font-size:100px;animation:shake 1.2s infinite alternate}@keyframes shake{to{transform:rotate(8deg) scale(1.08)}}.paper{max-width:760px;background:#fff8f1;color:#3b2430;border-radius:26px;padding:clamp(28px,6vw,65px);box-shadow:0 28px 80px #0007}.paper h2{color:#4a2638}.paper .copy{margin:auto}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;width:min(980px,94vw);margin-top:18px}.photo{padding:8px;background:#fff;border-radius:18px;transform:rotate(-1deg);box-shadow:0 16px 45px #0005}.photo:nth-child(even){transform:rotate(2deg)}.photo img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:12px;display:block}.empty{padding:35px;border:1px dashed #ffffff55;border-radius:20px;opacity:.8}.video-wrap{width:min(900px,94vw)}video{width:100%;border-radius:24px;background:#000;max-height:65vh}.stars{font-size:42px;letter-spacing:22px;animation:twinkle 2s infinite alternate}@keyframes twinkle{to{opacity:.45;transform:scale(1.05)}}.signature{font-family:'Dancing Script';font-size:clamp(32px,6vw,60px);color:var(--accent)}.finale{background:radial-gradient(circle at center,#ffffff12,transparent 50%)}.scene{position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden}.scene:before,.scene:after{content:"";position:absolute;inset:-20%;background-repeat:repeat;opacity:.7}.scene.shooting_stars:before{background:radial-gradient(circle,#fff 1px,transparent 2px);background-size:58px 58px;animation:drift 14s linear infinite}.scene.shooting_stars:after{background:linear-gradient(120deg,transparent 47%,#fff 49%,transparent 51%);background-size:280px 280px;animation:shoot 5s linear infinite}.scene.rose_petals:before{content:"🌹  💗  🌸  ❤️  🌹  💕";font-size:42px;word-spacing:70px;animation:falling 10s linear infinite}.scene.neon_hearts:before{content:"❤  ♥  ♡  ❤  ♥  ♡";font-size:80px;color:#ff5fb4;filter:drop-shadow(0 0 18px #ff4fd8);animation:pulse 3s ease-in-out infinite}.scene.romantic_sky:before{background:radial-gradient(circle,#fff 1px,transparent 2px);background-size:45px 45px;animation:drift 18s linear infinite}.scene.golden_sparkles:before{background:radial-gradient(circle,#ffd36a 1px,transparent 3px);background-size:45px 45px;animation:twinklebg 2s ease-in-out infinite alternate}.scene.polaroid_glow:before{background:linear-gradient(25deg,transparent 40%,#fff2 41% 48%,transparent 49%),linear-gradient(140deg,transparent 35%,#fff1 36% 48%,transparent 49%);background-size:260px 220px;animation:drift 20s linear infinite}.scene.bubbles:before{background:radial-gradient(circle at 20% 20%,#fff4 0 7px,transparent 8px),radial-gradient(circle at 70% 50%,#7fe8ff4a 0 13px,transparent 14px),radial-gradient(circle at 40% 80%,#fff3 0 9px,transparent 10px);background-size:140px 160px;animation:floatScene 9s linear infinite}.scene.confetti_party:before{background:linear-gradient(45deg,#ff4f9c 0 4px,transparent 4px 20px),linear-gradient(135deg,#ffd166 0 4px,transparent 4px 22px),linear-gradient(70deg,#72e7ff 0 4px,transparent 4px 24px);background-size:60px 70px;animation:drift 8s linear infinite}.scene.fireworks:before{background:radial-gradient(circle at 20% 25%,#fff 0 2px,transparent 3px),radial-gradient(circle at 75% 35%,#ffcf66 0 2px,transparent 3px),radial-gradient(circle at 45% 70%,#ff4fc4 0 2px,transparent 3px);background-size:160px 160px;animation:twinklebg 1.6s ease-in-out infinite alternate}.scene.mystic_fog:before{background:radial-gradient(ellipse at 30% 40%,#c786ff66,transparent 38%),radial-gradient(ellipse at 70% 65%,#7dffe144,transparent 40%);filter:blur(30px);animation:fog 10s ease-in-out infinite alternate}.scene.magic_portal:before{border:8px solid #7dffe188;border-radius:50%;width:52vmin;height:52vmin;inset:24vh auto auto 24vw;box-shadow:0 0 70px #7dffe1, inset 0 0 50px #7dffe1;animation:spin 12s linear infinite}.scene.lanterns:before{content:"🏮   🏮   🏮   🏮   🏮";font-size:58px;word-spacing:90px;animation:floatScene 7s ease-in-out infinite}.scene.fairy_lights:before{background:radial-gradient(circle,#ffe36e 0 5px,transparent 7px);background-size:80px 80px;filter:drop-shadow(0 0 10px #ffe36e);animation:twinklebg 1.5s ease-in-out infinite alternate}.scene.cinematic_aurora:before{background:linear-gradient(120deg,transparent 20%,#9f7cff55 40%,#7dffe155 55%,transparent 75%);filter:blur(40px);animation:aurora 8s ease-in-out infinite alternate}.scene.balloons:before{content:"🎈   🎈   🎈   🎈";font-size:72px;word-spacing:110px;animation:floatScene 8s ease-in-out infinite}.scene.party:before{content:"✨ 🎉 🎊 ✨ 🎉 🎊";font-size:55px;word-spacing:70px;animation:falling 7s linear infinite}@keyframes shoot{to{transform:translate(-35%,45%)}}@keyframes falling{to{transform:translateY(130vh) rotate(25deg)}}@keyframes pulse{50%{transform:scale(1.08);opacity:.4}}@keyframes twinklebg{to{opacity:.25;transform:scale(1.04)}}@keyframes floatScene{50%{transform:translateY(-12vh) translateX(3vw)}}@keyframes fog{to{transform:translateX(10%) scale(1.15);opacity:.35}}@keyframes spin{to{transform:rotate(360deg)}}@keyframes aurora{to{transform:translateX(8%) skewX(-8deg) scale(1.15)}}@media(max-width:600px){.option{width:calc(100% - 16px);margin:5px}}</style></head><body>__BANNER__<div class="scene __SCENE__"></div><div class="confetti"></div><main>
<section class="screen active" id="intro"><div class="emoji">__EMOJI__</div><p class="eyebrow">a premium __CATEGORY__ story</p><h1>__TITLE__</h1><p class="lead">__NAME__, are you ready for a little surprise?</p><button class="btn" onclick="go('choices')">START THE STORY ✨</button></section>
<section class="screen" id="choices"><p class="eyebrow">chapter one · choose your mood</p><div class="progress"><span></span></div><h2>Pick the <em>vibe</em> for this moment</h2><div class="choice"><button class="option" onclick="picked('Cute & Sweet 🥹')">🥹 Cute & Sweet</button><button class="option" onclick="picked('Fun & Crazy 🤪')">🤪 Fun & Crazy</button><button class="option" onclick="picked('Emotional ❤️')">❤️ Emotional</button><button class="option" onclick="picked('Main Character 👑')">👑 Main Character</button></div><p id="picked"></p><button class="btn" onclick="go('reveal')">CONTINUE →</button></section>
<section class="screen" id="reveal"><p class="eyebrow">chapter two · the surprise</p><div class="gift">🎁</div><h2>Something <em>special</em> is waiting…</h2><button class="btn" onclick="document.getElementById('secret').hidden=false;this.hidden=true">OPEN THE SURPRISE</button><div id="secret" hidden><p class="lead">__SURPRISE__</p><button class="btn" onclick="go('letter')">READ THE LETTER 💌</button></div></section>
<section class="screen" id="letter"><p class="eyebrow">chapter three · from the heart</p><div class="paper"><h2>For <em>__NAME__</em> ❤️</h2><div class="copy" id="type"></div><button class="btn" onclick="go('memories')">SEE OUR MEMORIES →</button></div></section>
<section class="screen" id="memories"><p class="eyebrow">chapter four · our memories</p><h2>Moments we <em>won't forget</em></h2><div class="gallery">__PHOTOS__</div><button class="btn" onclick="go('video')">ONE MORE SURPRISE ↓</button></section>
<section class="screen" id="video"><p class="eyebrow">chapter five · press play</p><h2>A little <em>movie</em> for you 🎬</h2><div class="video-wrap">__VIDEO__</div><button class="btn" onclick="go('finale')">FINISH THE STORY ✨</button></section>
<section class="screen finale" id="finale"><div class="stars">✦ · ✧ · ✦ · ✧</div><div class="emoji">__EMOJI__</div><p class="eyebrow">and one last thing…</p><h2>__TITLE__</h2><p class="lead">__MESSAGE__</p><div class="signature">With love, always 💖</div><button class="btn" onclick="go('intro')">REPLAY THE MAGIC ↻</button></section></main><script>const text=__LETTER_JSON__;function go(id){document.querySelectorAll('.screen').forEach(x=>x.classList.toggle('active',x.id===id));window.scrollTo({top:0,behavior:'smooth'});if(id==='letter')type()}function picked(x){document.getElementById('picked').textContent='Your mood: '+x}let typed=false;function type(){if(typed)return;typed=true;let i=0,e=document.getElementById('type');(function t(){e.textContent=text.slice(0,i++);if(i<=text.length)setTimeout(t,12)})()}</script></body></html>'''
    replacements = {
        "__TITLE__": title, "__NAME__": name, "__CATEGORY__": category,
        "__ACCENT__": cfg["accent"], "__BG__": cfg["bg"], "__EMOJI__": cfg["emoji"],
        "__SURPRISE__": escape(site.get("surprise_text") or "You are more special than words can explain. ✨"),
        "__PHOTOS__": photo_cards, "__VIDEO__": video, "__MESSAGE__": message,
        "__LETTER_JSON__": json.dumps(escape(site.get("letter_text") or site.get("message") or "A special message from my heart.")),
        "__BANNER__": "<div class='preview'>PRIVATE PREVIEW • EXPIRES SOON</div>" if preview else "",
        "__SCENE__": scene
    }
    for key, value in replacements.items():
        html = html.replace(key, value)
    return HTMLResponse(html)

def render_site(site, preview=False, preview_token=None):
    if site.get("package") == "premium":
        return render_premium_story(site, preview, preview_token)
    theme = THEMES.get(site.get("theme"), THEMES["starry_night"])
    title = escape(site.get("title", "A Special Surprise"))
    message = escape(site.get("message", ""))
    name = escape(site.get("recipient_name", ""))
    accent, bg = theme["accent"], theme["bg"]
    effect = theme["effect"]

    title_font, title_google = FONT_MAP.get(site.get("title_font"), FONT_MAP.get(site.get("font"), FONT_MAP["playfair"]))
    message_font, message_google = FONT_MAP.get(site.get("message_font"), FONT_MAP.get(site.get("font"), FONT_MAP["inter"]))
    font_url = f"https://fonts.googleapis.com/css2?family={title_google}&family={message_google}&display=swap"
    extras = set(site.get("extras", []))
    surprise_html = ""
    if "reveal" in extras:
        surprise_html = f"<section class='surprise'><button onclick='revealSurprise(this)'>🎁 Click Here to Reveal Your Surprise</button><div class='secret'>{escape(site.get('surprise_text','A special surprise just for you! ✨'))}</div></section>"
    if "letter" in extras:
        surprise_html += f"<section class='letter'><button onclick='openLetter(this)'>💌 Open My Secret Letter</button><div class='letter-text'>{escape(site.get('letter_text','You mean more to me than words can say. 💖'))}</div></section>"
    if "confetti" in extras:
        surprise_html += "<button class='celebrate' onclick='celebrate()'>🎉 Celebrate!</button><div id='confetti'></div>"

    media_suffix = f"?token={quote(preview_token)}" if preview and preview_token else ""
    photos = site.get("photo_file_ids", [])
    photo_html = ""
    if photos:
        if len(photos) == 1:
            photo_html = f"<div class='hero-photo'><img src='/media/{site['slug']}/photo/0{media_suffix}' alt='Special memory'></div>"
        else:
            cards = "".join(
                f"<img src='/media/{site['slug']}/photo/{i}{media_suffix}' alt='Memory {i+1}' loading='lazy'>"
                for i in range(len(photos))
            )
            photo_html = f"<section class='gallery'><div class='gallery-head'>Beautiful Memories ✨</div><div class='gallery-grid'>{cards}</div></section>"

    video_html = ""
    if site.get("video_file_id"):
        video_html = (
            f"<section class='video-section'><div class='gallery-head'>A Special Video 🎬</div>"
            f"<video controls playsinline preload='metadata' src='/media/{site['slug']}/video{media_suffix}'></video></section>"
        )

    preview_banner = "<div class='preview-banner'>🔒 PRIVATE 2-MINUTE PREVIEW — NOT PUBLISHED</div>" if preview else ""
    recipient = f"<div class='to'>For {name} ✨</div>" if name else ""

    fireworks = "".join(
        "<span class='burst' style='--x:%d%%;--y:%d%%'></span>" % (x, y)
        for x, y in [(8,20),(20,35),(37,16),(55,28),(72,18),(88,33)]
    ) if "fireworks" in effect else ""
    hearts = "<div class='float hearts'>💖 ♥ 💕 💗 ♡ 💓</div>" if ("heart" in effect or "petals" in effect) else ""
    stars = "<div class='float stars'>✦ ✧ ✦ ✨ ⋆ ✧ ✦ ✨</div>" if ("stars" in effect or "nebula" in effect) else ""
    lanterns = "<div class='float lanterns'>🏮 🏮 🏮 🏮</div>" if "lantern" in effect else ""
    rain = "<div class='rain'></div>" if "rain" in effect else ""
    particles = "<div class='particles'></div>" if ("particles" in effect or "gold" in effect or "lights" in effect) else ""

    premium_html = ""
    if site.get("package") == "premium":
        premium_html = """
<section class="section premium-journey">
  <div class="chapter-nav"><span>01 · Welcome</span><span>02 · Memories</span><span>03 · Surprise</span><span>04 · Finale</span></div>
  <div class="interactive-grid">
    <div class="interactive-card" onclick="this.querySelector('.hidden-reveal').style.display='block'">🎁<br><b>Open a Surprise</b><div class="hidden-reveal">You are more special than words can explain ✨</div></div>
    <div class="interactive-card" onclick="this.querySelector('.hidden-reveal').style.display='block'">💌<br><b>Open My Letter</b><div class="hidden-reveal">A special message was waiting for you ❤️</div></div>
    <div class="interactive-card" onclick="this.querySelector('.hidden-reveal').style.display='block'">🕯️<br><b>Make a Wish</b><div class="hidden-reveal">Close your eyes and make your best wish 🌟</div></div>
  </div>
  <div class="star-field">
    <span class="star" style="left:12%;top:25%" onclick="this.innerHTML='💖'">✦</span>
    <span class="star" style="left:42%;top:55%" onclick="this.innerHTML='🎁'">✦</span>
    <span class="star" style="left:70%;top:18%" onclick="this.innerHTML='✨'">✦</span>
    <span class="star" style="left:82%;top:70%" onclick="this.innerHTML='❤️'">✦</span>
  </div>
  <div class="cinematic-final"><h2>One Last Thing... ❤️</h2><p>Thank you for being part of this beautiful story.</p><button onclick="this.innerHTML='🎆 Surprise Unlocked! 🎆';document.body.classList.add('celebrate')">Click for the Final Surprise</button></div>
</section>
"""

    return HTMLResponse(f"""<!doctype html>
<html><head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{title}</title>
<link rel='preconnect' href='https://fonts.googleapis.com'>
<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>
<link href='{font_url}' rel='stylesheet'>
<style>
:root{{--accent:{accent};--bg:{bg};--titlefont:'{title_font}',serif;--messagefont:'{message_font}',Inter,Arial,sans-serif}}
*{{box-sizing:border-box}}
html{{scroll-behavior:smooth}}
body{{margin:0;min-height:100vh;color:#fff;font-family:var(--messagefont);background:var(--bg);overflow-x:hidden}}
body:before{{content:'';position:fixed;inset:0;background:radial-gradient(circle at 50% 42%,rgba(255,255,255,.08),transparent 36%),radial-gradient(circle at 10% 15%,var(--accent),transparent 18%);opacity:.35;filter:blur(18px);animation:breathe 6s ease-in-out infinite;pointer-events:none}}
.wrap{{position:relative;z-index:3;width:min(1040px,92vw);margin:0 auto;padding:90px 0 70px}}
.card{{padding:clamp(34px,6vw,68px) clamp(20px,5vw,50px);text-align:center;border:1px solid rgba(255,255,255,.2);border-radius:32px;background:rgba(5,7,22,.30);backdrop-filter:blur(16px);box-shadow:0 28px 100px rgba(0,0,0,.45)}}
h1{{font-family:var(--titlefont);margin:8px 0 18px;font-size:clamp(2.5rem,9vw,6.8rem);line-height:1.02;color:var(--accent);text-shadow:0 0 12px color-mix(in srgb,var(--accent) 70%,transparent),0 0 45px color-mix(in srgb,var(--accent) 45%,transparent)}}
.to{{font-family:Inter,Arial,sans-serif;font-size:.95rem;letter-spacing:.16em;text-transform:uppercase;opacity:.9}}
.message{{white-space:pre-wrap;font-family:var(--messagefont);font-size:clamp(1.08rem,2.7vw,1.6rem);line-height:1.8;max-width:780px;margin:0 auto}}
.badge{{margin-top:32px;opacity:.72;font-family:Inter,Arial,sans-serif;font-size:.9rem}}
.preview-banner{{position:fixed;z-index:20;top:0;left:0;right:0;padding:11px;text-align:center;background:rgba(0,0,0,.72);font-family:Inter,Arial,sans-serif;font-weight:700;letter-spacing:.05em}}
.hero-photo{{margin:30px auto 0;width:min(520px,100%);padding:8px;border-radius:28px;background:linear-gradient(135deg,rgba(255,255,255,.7),var(--accent),rgba(255,255,255,.25));box-shadow:0 22px 70px rgba(0,0,0,.35)}}
.hero-photo img{{display:block;width:100%;max-height:560px;object-fit:cover;border-radius:22px}}
.gallery,.video-section{{margin-top:34px;padding:24px;border:1px solid rgba(255,255,255,.18);border-radius:28px;background:rgba(5,7,22,.28);backdrop-filter:blur(14px)}}
.gallery-head{{font-family:Inter,Arial,sans-serif;font-weight:700;font-size:1.05rem;letter-spacing:.04em;margin-bottom:18px;color:var(--accent)}}
.gallery-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}}
.gallery-grid img{{width:100%;aspect-ratio:1/1;object-fit:cover;border-radius:18px;border:1px solid rgba(255,255,255,.18);transition:transform .25s ease,box-shadow .25s ease}}
.gallery-grid img:hover{{transform:translateY(-5px) scale(1.02);box-shadow:0 16px 35px rgba(0,0,0,.3)}}
.surprise,.letter{{margin:30px auto 0;max-width:720px}}.surprise button,.letter button,.celebrate{{border:0;border-radius:999px;padding:16px 26px;font-family:Inter,Arial,sans-serif;font-weight:800;font-size:1rem;cursor:pointer;background:linear-gradient(135deg,var(--accent),#fff);color:#111;box-shadow:0 15px 40px rgba(0,0,0,.28);transition:.25s}}.surprise button:hover,.letter button:hover,.celebrate:hover{{transform:translateY(-3px) scale(1.03)}}.secret,.letter-text{{display:none;margin-top:18px;padding:24px;border-radius:22px;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.22);white-space:pre-wrap;animation:pop .5s ease both}}.surprise.open .secret,.letter.open .letter-text{{display:block}}.celebrate{{margin-top:26px}}.confetti-piece{{position:fixed;width:10px;height:16px;top:-20px;z-index:30;animation:fall 3.5s linear forwards}}@keyframes pop{{from{{opacity:0;transform:scale(.92)}}to{{opacity:1;transform:scale(1)}}}}@keyframes fall{{to{{transform:translateY(110vh) rotate(900deg);opacity:0}}}}.video-section video{{display:block;width:100%;max-height:560px;border-radius:20px;background:#000;border:1px solid rgba(255,255,255,.15)}}
.float{{position:fixed;inset:auto 0 -20px 0;z-index:1;display:flex;justify-content:space-around;font-size:clamp(24px,4vw,56px);opacity:.75;animation:floatup 10s linear infinite;pointer-events:none}}
.stars{{top:4%;bottom:auto;animation:twinkle 4s ease-in-out infinite alternate;word-spacing:4vw}}
.hearts{{animation-duration:12s}}.lanterns{{animation-duration:16s}}
.particles{{position:fixed;inset:0;z-index:1;background-image:radial-gradient(circle,rgba(255,255,255,.9) 1px,transparent 1.5px),radial-gradient(circle,var(--accent) 1px,transparent 2px);background-size:53px 53px,89px 89px;animation:drift 14s linear infinite;opacity:.5;pointer-events:none}}
.rain{{position:fixed;inset:-20% 0 0;background:repeating-linear-gradient(110deg,transparent 0 18px,rgba(255,255,255,.18) 19px 20px,transparent 21px 45px);animation:rain 1s linear infinite;opacity:.5;pointer-events:none}}
.burst{{position:fixed;left:var(--x);top:var(--y);width:12px;height:12px;border-radius:50%;background:#fff;box-shadow:0 0 18px 8px var(--accent),25px 25px 0 -3px #ffcc66,-25px 25px 0 -3px #fff,-30px -18px 0 -3px #ff4fc4,30px -18px 0 -3px #7be7ff,0 38px 0 -3px #ffdb6b;animation:burst 2.8s ease-out infinite;pointer-events:none}}
@keyframes floatup{{from{{transform:translateY(20vh) rotate(0)}}to{{transform:translateY(-130vh) rotate(20deg)}}}}
@keyframes twinkle{{from{{opacity:.3;transform:scale(.9)}}to{{opacity:1;transform:scale(1.08)}}}}
@keyframes burst{{0%,100%{{transform:scale(.4);opacity:0}}20%{{transform:scale(1.1);opacity:1}}65%{{transform:scale(1.7);opacity:.7}}}}
@keyframes rain{{to{{transform:translateY(22%)}}}}
@keyframes drift{{to{{transform:translate(50px,90px)}}}}
@keyframes breathe{{50%{{transform:scale(1.08);opacity:.55}}}}
@media(max-width:600px){{.wrap{{width:94vw;padding:64px 0 36px}}.card{{border-radius:24px}}.gallery-grid{{grid-template-columns:repeat(2,1fr)}}}}

/* Premium interactive experience */
.premium-experience{{position:relative;overflow:hidden}}
.chapter-nav{{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin:24px 0}}
.chapter-nav span{{padding:8px 12px;border:1px solid rgba(255,255,255,.2);border-radius:999px;background:rgba(255,255,255,.08)}}
.interactive-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin:22px 0}}
.interactive-card{{cursor:pointer;padding:20px;border-radius:22px;background:rgba(255,255,255,.1);backdrop-filter:blur(12px);border:1px solid rgba(255,255,255,.18);transition:.25s}}
.interactive-card:hover{{transform:translateY(-5px) scale(1.02)}}
.star-field{{position:relative;min-height:220px;border-radius:24px;background:rgba(0,0,0,.22);overflow:hidden}}
.star{{position:absolute;font-size:28px;cursor:pointer;filter:drop-shadow(0 0 10px currentColor)}}
.hidden-reveal{{display:none;margin-top:14px;padding:18px;border-radius:18px;background:rgba(255,255,255,.12)}}
.cinematic-final{{margin-top:30px;padding:42px 20px;border-radius:28px;text-align:center;background:linear-gradient(135deg,rgba(255,255,255,.12),rgba(255,255,255,.03))}}
</style>
</head><body>
{preview_banner}{particles}{stars}{hearts}{lanterns}{rain}{fireworks}
<div class='wrap'><main class='card'>{recipient}<h1>{title}</h1><div class='message'>{message}</div>{photo_html}{video_html}{surprise_html}<div class='badge'>✨ Created with WishVerse ✨</div></main></div>
<script>function revealSurprise(b){{b.parentElement.classList.toggle('open');b.textContent=b.parentElement.classList.contains('open')?'✨ Surprise Revealed!':'🎁 Click Here to Reveal Your Surprise'}}function openLetter(b){{b.parentElement.classList.toggle('open');b.textContent=b.parentElement.classList.contains('open')?'💖 Letter Opened':'💌 Open My Secret Letter'}}function celebrate(){{for(let i=0;i<90;i++){{let e=document.createElement('i');e.className='confetti-piece';e.style.left=Math.random()*100+'vw';e.style.transform='rotate('+Math.random()*360+'deg)';e.style.animationDelay=Math.random()*0.7+'s';e.style.background='hsl('+Math.random()*360+' 90% 65%)';document.body.appendChild(e);setTimeout(()=>e.remove(),4500)}}}}</script>
{premium_html}

</body></html>""")

@app.get("/s/{slug}", response_class=HTMLResponse)
async def public_website(slug: str):
    site = await authorized_site(slug)
    return render_site(site)

@app.get("/preview/{slug}", response_class=HTMLResponse)
async def preview_website(slug: str, token: str):
    site = await authorized_site(slug, token)
    return render_site(site, preview=True, preview_token=token)
