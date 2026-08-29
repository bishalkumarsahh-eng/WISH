from contextlib import asynccontextmanager
from datetime import datetime, timezone
from html import escape
from urllib.parse import quote
import httpx

from fastapi import FastAPI, HTTPException, Response, Query
from fastapi.responses import HTMLResponse
from .config import BOT_TOKEN
from .db import db, setup_indexes
from .themes import THEMES, PREMIUM_THEMES

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

def render_site(site, preview=False, preview_token=None):
    theme = (PREMIUM_THEMES.get(site.get("premium_theme") or site.get("theme")) if site.get("package") == "premium" else None) or THEMES.get(site.get("theme"), THEMES["starry_night"])
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
        occasion = site.get("type", "custom")
        premium_theme = PREMIUM_THEMES.get(site.get("premium_theme") or site.get("theme"), {})
        theme_name = escape(premium_theme.get("name", "💎 Premium Story"))
        journey = {
            "birthday": ("🎂", "Are you ready for your birthday surprise?", "Pick your birthday mood", "Open the final birthday surprise"),
            "valentine": ("❤️", "A love story made specially for you…", "Choose your love mood", "Unlock our final love surprise"),
            "anniversary": ("💍", "Another beautiful chapter begins here…", "Remember our journey", "Open our forever surprise"),
            "friendship": ("🫶", "Warning: crazy memories ahead!", "Choose our friendship vibe", "Open the bestie surprise"),
            "congratulations": ("🏆", "This moment deserves a celebration!", "Choose your victory mood", "Unlock the celebration"),
            "surprise": ("🎁", "Something is waiting behind every chapter…", "Choose your mystery path", "Reveal the final surprise"),
            "festival": ("✨", "Let the celebration lights begin…", "Choose the festive mood", "Open the final celebration"),
            "custom": ("🌟", "A story made only for you…", "Choose your journey", "Unlock the finale"),
        }.get(occasion, ("🌟", "A story made only for you…", "Choose your journey", "Unlock the finale"))
        icon, intro_line, choice_line, finale_line = journey
        safe_surprise = escape(site.get('surprise_text','You are more special than words can explain ✨'))
        safe_letter = escape(site.get('letter_text','A special message was waiting here for you. 💖'))
        premium_html = f"""
<section class="premium-experience" data-premium-theme="{escape(site.get('premium_theme',''))}">
  <div class="premium-theme-pill">{theme_name}</div>
  <section class="journey-screen journey-intro">
    <div class="premium-orbit">{icon} <span>✦</span> ✧ <span>✦</span></div>
    <p class="journey-kicker">A PREMIUM INTERACTIVE EXPERIENCE</p>
    <h2>{intro_line}</h2>
    <p class="journey-sub">Tap below and move through the story one beautiful chapter at a time.</p>
    <button class="journey-button" onclick="nextJourney('j-choice')">BEGIN THE JOURNEY ✨</button>
  </section>
  <section id="j-choice" class="journey-screen journey-hidden">
    <p class="journey-kicker">CHAPTER ONE</p><h2>{choice_line}</h2>
    <div class="mood-grid">
      <button onclick="pickMood(this,'✨ Magical')">✨ Magical</button><button onclick="pickMood(this,'💖 Emotional')">💖 Emotional</button>
      <button onclick="pickMood(this,'🎉 Party')">🎉 Party</button><button onclick="pickMood(this,'🌙 Dreamy')">🌙 Dreamy</button>
    </div>
    <div id="mood-result" class="mood-result"></div>
    <button class="journey-button" onclick="nextJourney('j-memories')">CONTINUE →</button>
  </section>
  <section id="j-memories" class="journey-screen journey-hidden">
    <p class="journey-kicker">CHAPTER TWO · MEMORIES</p><h2>Every picture tells part of the story.</h2>
    <div class="premium-memory-strip">{photo_html or '<div class="memory-empty">📸 Your beautiful memories belong here.</div>'}</div>
    <button class="journey-button" onclick="nextJourney('j-surprise')">ONE MORE SURPRISE 🎁</button>
  </section>
  <section id="j-surprise" class="journey-screen journey-hidden">
    <p class="journey-kicker">CHAPTER THREE · A SECRET</p><h2>There is something waiting for you…</h2>
    <button class="big-gift" onclick="openPremiumGift(this)">🎁<span>CLICK TO OPEN</span></button>
    <div id="premium-gift" class="premium-secret">{safe_surprise}</div>
    <button class="letter-button" onclick="togglePremiumLetter()">💌 OPEN MY LETTER</button>
    <div id="premium-letter" class="premium-letter">{safe_letter}</div>
    <button class="journey-button" onclick="nextJourney('j-finale')">{finale_line} ✨</button>
  </section>
  <section id="j-finale" class="journey-screen journey-finale journey-hidden">
    <div class="finale-stars">✦ ✧ ✦ ✨ ✦</div><p class="journey-kicker">THE FINAL CHAPTER</p>
    <h2>{title}</h2><p class="premium-finale-copy">{message}</p>
    {video_html}
    <button class="journey-button" onclick="premiumCelebrate()">CELEBRATE THIS MOMENT 🎆</button>
    <button class="replay-journey" onclick="replayJourney()">↻ Replay the magic</button>
  </section>
</section>
"""
        # Premium journey already places media in its chapters.
        photo_html = ""
        video_html = ""

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
.premium-theme-pill{{display:inline-block;margin:30px auto 12px;padding:9px 16px;border-radius:999px;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.25);font-weight:800}}
.journey-screen{{margin-top:26px;padding:clamp(26px,5vw,52px);border-radius:30px;text-align:center;background:linear-gradient(145deg,rgba(255,255,255,.12),rgba(255,255,255,.035));border:1px solid rgba(255,255,255,.18);box-shadow:0 25px 70px rgba(0,0,0,.25);transition:.55s ease}}
.journey-hidden{{display:none}}.journey-kicker{{letter-spacing:.16em;font-size:.72rem;font-weight:800;opacity:.72}}.journey-screen h2{{font-family:var(--titlefont);font-size:clamp(2rem,6vw,4.6rem);color:var(--accent);margin:10px 0 18px}}.journey-sub{{max-width:640px;margin:0 auto 22px;line-height:1.7}}
.premium-orbit{{font-size:clamp(3rem,9vw,6rem);letter-spacing:.25em;animation:orbitGlow 3s ease-in-out infinite}}.premium-orbit span{{display:inline-block;animation:spinStar 4s linear infinite}}.journey-button,.letter-button{{margin-top:22px;border:0;border-radius:999px;padding:15px 25px;font-weight:900;cursor:pointer;background:linear-gradient(135deg,var(--accent),#fff);color:#111;box-shadow:0 14px 36px rgba(0,0,0,.25)}}
.mood-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;max-width:620px;margin:24px auto}}.mood-grid button{{padding:18px;border-radius:20px;border:1px solid rgba(255,255,255,.2);background:rgba(255,255,255,.1);color:#fff;font-weight:800;cursor:pointer}}.mood-grid button:hover,.mood-grid button.selected{{background:var(--accent);color:#111;transform:translateY(-3px)}}.mood-result{{min-height:26px;font-weight:800;color:var(--accent)}}
.premium-memory-strip .gallery{{margin-top:0}}.premium-memory-strip .hero-photo{{margin-top:0}}.memory-empty{{padding:55px 20px;border:1px dashed rgba(255,255,255,.35);border-radius:24px;font-size:1.05rem;opacity:.9}}
.big-gift{{display:flex;flex-direction:column;gap:8px;align-items:center;justify-content:center;margin:22px auto;border:0;border-radius:50%;width:160px;height:160px;background:radial-gradient(circle,#fff,var(--accent));font-size:4rem;cursor:pointer;box-shadow:0 0 0 12px rgba(255,255,255,.08),0 0 55px var(--accent);transition:.3s}}.big-gift:hover{{transform:scale(1.08) rotate(-4deg)}}.big-gift span{{font-size:.72rem;font-weight:900;color:#222}}.premium-secret,.premium-letter{{display:none;margin:18px auto 0;max-width:700px;padding:24px;border-radius:22px;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.2);white-space:pre-wrap;line-height:1.7;animation:pop .5s ease both}}.premium-secret.open,.premium-letter.open{{display:block}}
.journey-finale{{background:radial-gradient(circle at top,rgba(255,255,255,.18),rgba(255,255,255,.04))}}.finale-stars{{font-size:2rem;letter-spacing:.3em;animation:twinkle 2s ease-in-out infinite alternate}}.premium-finale-copy{{white-space:pre-wrap;max-width:760px;margin:0 auto;line-height:1.8;font-size:1.08rem}}.replay-journey{{display:block;margin:18px auto 0;border:0;background:none;color:#fff;opacity:.8;cursor:pointer}}
@keyframes orbitGlow{{50%{{transform:translateY(-8px) scale(1.04);filter:drop-shadow(0 0 18px var(--accent))}}}}@keyframes spinStar{{to{{transform:rotate(360deg)}}}}

</style>
</head><body>
{preview_banner}{particles}{stars}{hearts}{lanterns}{rain}{fireworks}
<div class='wrap'><main class='card'>{recipient}<h1>{title}</h1><div class='message'>{message}</div>{photo_html}{video_html}{surprise_html}<div class='badge'>✨ Created with WishVerse ✨</div></main></div>
<script>function revealSurprise(b){{b.parentElement.classList.toggle('open');b.textContent=b.parentElement.classList.contains('open')?'✨ Surprise Revealed!':'🎁 Click Here to Reveal Your Surprise'}}function openLetter(b){{b.parentElement.classList.toggle('open');b.textContent=b.parentElement.classList.contains('open')?'💖 Letter Opened':'💌 Open My Secret Letter'}}function celebrate(){{for(let i=0;i<90;i++){{let e=document.createElement('i');e.className='confetti-piece';e.style.left=Math.random()*100+'vw';e.style.transform='rotate('+Math.random()*360+'deg)';e.style.animationDelay=Math.random()*0.7+'s';e.style.background='hsl('+Math.random()*360+' 90% 65%)';document.body.appendChild(e);setTimeout(()=>e.remove(),4500)}}}}function nextJourney(id){{const target=document.getElementById(id);if(target){{target.classList.remove('journey-hidden');setTimeout(()=>target.scrollIntoView({{behavior:'smooth',block:'center'}}),60)}}}}function pickMood(btn,label){{document.querySelectorAll('.mood-grid button').forEach(x=>x.classList.remove('selected'));btn.classList.add('selected');document.getElementById('mood-result').textContent='Perfect choice: '+label+' ✨'}}function openPremiumGift(btn){{btn.style.transform='scale(.85) rotate(12deg)';document.getElementById('premium-gift').classList.add('open');setTimeout(()=>btn.style.display='none',350)}}function togglePremiumLetter(){{document.getElementById('premium-letter').classList.toggle('open')}}function premiumCelebrate(){{celebrate();document.body.classList.add('celebrate')}}function replayJourney(){{document.querySelectorAll('.journey-screen').forEach((x,i)=>{{if(i>0)x.classList.add('journey-hidden')}});window.scrollTo({{top:0,behavior:'smooth'}})}}</script>
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
