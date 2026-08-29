from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from html import escape
from urllib.parse import quote
import httpx

from fastapi import FastAPI, HTTPException, Response, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from .config import BOT_TOKEN, PREVIEW_SECONDS
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
    # A preview timer starts on the first successful open, not when the
    # preview link is generated. This gives the creator a full 2 minutes.
    return expires is None or expires > datetime.now(timezone.utc)

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

        # Activate the 2-minute preview window on first open. The conditional
        # update prevents repeated requests from resetting the timer.
        if site.get("preview_expires_at") is None:
            now = datetime.now(timezone.utc)
            expires = now + timedelta(seconds=PREVIEW_SECONDS)
            activated = await db.websites.update_one(
                {"_id": site["_id"], "preview_token": token, "preview_expires_at": None},
                {"$set": {"preview_activated_at": now, "preview_expires_at": expires}},
            )
            if activated.modified_count:
                site["preview_activated_at"] = now
                site["preview_expires_at"] = expires
            else:
                site = await db.websites.find_one({"_id": site["_id"]})

        if not is_preview_valid(site, token):
            raise HTTPException(403, "Preview expired — create a new preview to continue")
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

@app.get("/media/{slug}/audio")
async def site_audio(slug: str, token: str | None = Query(default=None)):
    # Audio is intentionally a dedicated endpoint so the browser can request
    # the song independently of the HTML document.  It works for both preview
    # (token protected) and published premium websites.
    site = await authorized_site(slug, token)
    file_id = site.get("song_file_id")
    if not file_id:
        raise HTTPException(404, "Song not found")
    content, content_type = await get_media_bytes(file_id)
    stored_type = site.get("song_mime_type")
    if stored_type and stored_type.startswith("audio/"):
        content_type = stored_type
    if not content_type or content_type == "application/octet-stream":
        content_type = "audio/mpeg"
    # Returning Accept-Ranges makes playback more reliable on mobile Safari,
    # Chrome and Telegram's in-app browser.
    headers = {
        "Cache-Control": "public, max-age=3600",
        "Accept-Ranges": "bytes",
        "Content-Disposition": "inline",
    }
    return Response(content=content, media_type=content_type, headers=headers)


def render_premium_story_legacy(site, preview=False, preview_token=None):
    import json
    cfg = PREMIUM_THEME_CONFIG.get(site.get("premium_theme") or site.get("theme"), PREMIUM_THEME_CONFIG["custom_cinematic"])
    scene = cfg.get("scene", "shooting_stars")
    theme_key = site.get("premium_theme") or site.get("theme") or "custom_cinematic"
    page_style_map = {
        "birthday_flower_garden":"garden", "birthday_butterfly":"garden", "valentine_pink_garden":"garden", "valentine_cherry":"garden", "anniversary_flower":"garden",
        "birthday_cake":"party", "birthday_party":"party", "birthday_candy":"party", "congrats_confetti":"party", "congrats_fireworks":"party",
        "valentine_rose":"envelope", "valentine_candle":"envelope", "valentine_neon":"neon", "valentine_stars":"cinematic",
        "anniversary_memory":"scrapbook", "anniversary_beach":"postcard", "anniversary_gold":"luxury", "anniversary_twilight":"cinematic",
        "friendship_besties":"scrapbook", "friendship_crazy":"arcade", "friendship_arcade":"arcade", "friendship_sunset":"postcard",
        "congrats_victory":"luxury", "congrats_spotlight":"stage", "surprise_mystery":"mystery", "surprise_magic":"portal",
        "festival_lantern":"lantern", "festival_lights":"party", "custom_cinematic":"cinematic"
    }
    page_style = cfg.get("page_style") or page_style_map.get(theme_key) or "cinematic"
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
    song_html = (f"<audio id='wx-song' preload='auto' loop autoplay playsinline src='/media/{site['slug']}/audio{token_q}'></audio>"
                 if site.get("song_file_id") else "")
    html = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title><link href="https://fonts.googleapis.com/css2?family=Dancing+Script:wght@500;700&family=DM+Sans:wght@400;700;800&family=Nunito:wght@700;800;900&display=swap" rel="stylesheet"><style>
:root{--accent:__ACCENT__;--bg:__BG__}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:#fff;font-family:'DM Sans',sans-serif;overflow-x:hidden}.preview{position:fixed;top:0;left:0;right:0;z-index:99;background:#111d;padding:10px;text-align:center;font-weight:800;font-size:12px}.confetti{position:fixed;inset:0;pointer-events:none;z-index:0;background-image:radial-gradient(circle,#fff 1px,transparent 1.5px),radial-gradient(circle,var(--accent) 1px,transparent 2px);background-size:52px 52px,87px 87px;opacity:.45;animation:drift 16s linear infinite}@keyframes drift{to{transform:translate(50px,100px)}}main{position:relative;z-index:1}.screen{display:none;min-height:100svh;padding:76px 20px 42px;align-items:center;justify-content:center;text-align:center}.screen.active{display:flex;flex-direction:column}.eyebrow{text-transform:uppercase;letter-spacing:.16em;font-size:11px;opacity:.72}.emoji{font-size:clamp(64px,13vw,130px);filter:drop-shadow(0 12px 30px #0007);animation:bob 3s ease-in-out infinite}@keyframes bob{50%{transform:translateY(-12px) rotate(4deg)}}h1,h2{font-family:'Nunito',sans-serif;margin:12px 0;line-height:1.02}h1{font-size:clamp(42px,10vw,90px)}h2{font-size:clamp(30px,7vw,58px)}em{color:var(--accent);font-family:'Dancing Script',cursive;font-size:1.25em}.lead,.copy{max-width:700px;line-height:1.8;font-size:clamp(16px,2.5vw,20px);white-space:pre-wrap}.btn.opening-envelope{border-radius:4px;background:#fff4e6;clip-path:polygon(0 0,100% 0,100% 75%,50% 100%,0 75%)}.btn.opening-gift{border-radius:16px;background:linear-gradient(135deg,#ff4f8b,#ffd166)}.btn.opening-flower{border-radius:50px 12px 50px 12px}.btn.opening-cinematic{border-radius:6px;letter-spacing:.14em}.btn.opening-portal{border-radius:50%;width:150px;height:150px;background:radial-gradient(circle,#fff,#7dffe1,#111)}.btn.opening-luxury{border-radius:0;border:1px solid #ffd36a;background:#140f05;color:#ffd36a}.btn.opening-neon{background:#100016;color:#ff5fd2;border:2px solid #ff5fd2;box-shadow:0 0 25px #ff4fd8}.btn.opening-arcade{border-radius:0;font-family:monospace;box-shadow:8px 8px 0 #000}.btn.opening-elegant{background:linear-gradient(135deg,#fff,var(--accent))}.btn,.option{border:0;border-radius:999px;padding:16px 25px;margin:8px;font:800 16px 'DM Sans';cursor:pointer;background:#fff;color:#17111b;box-shadow:0 14px 35px #0005;transition:.25s}.btn:hover,.option:hover{transform:translateY(-4px) scale(1.03)}.option{background:#ffffff18;color:#fff;border:1px solid #ffffff30}.choice{display:flex;flex-wrap:wrap;justify-content:center;max-width:700px}.progress{height:5px;width:min(500px,80vw);background:#ffffff22;border-radius:9px;margin:14px}.progress span{display:block;height:100%;width:50%;background:var(--accent);border-radius:9px}.gift{font-size:100px;animation:shake 1.2s infinite alternate}@keyframes shake{to{transform:rotate(8deg) scale(1.08)}}.paper{max-width:760px;background:#fff8f1;color:#3b2430;border-radius:26px;padding:clamp(28px,6vw,65px);box-shadow:0 28px 80px #0007}.paper h2{color:#4a2638}.paper .copy{margin:auto}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;width:min(980px,94vw);margin-top:18px}.photo{padding:8px;background:#fff;border-radius:18px;transform:rotate(-1deg);box-shadow:0 16px 45px #0005}.photo:nth-child(even){transform:rotate(2deg)}.photo img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:12px;display:block}.empty{padding:35px;border:1px dashed #ffffff55;border-radius:20px;opacity:.8}.video-wrap{width:min(900px,94vw)}video{width:100%;border-radius:24px;background:#000;max-height:65vh}.stars{font-size:42px;letter-spacing:22px;animation:twinkle 2s infinite alternate}@keyframes twinkle{to{opacity:.45;transform:scale(1.05)}}.signature{font-family:'Dancing Script';font-size:clamp(32px,6vw,60px);color:var(--accent)}.finale{background:radial-gradient(circle at center,#ffffff12,transparent 50%)}.scene{position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden}.scene:before,.scene:after{content:"";position:absolute;inset:-20%;background-repeat:repeat;opacity:.7}.scene.shooting_stars:before{background:radial-gradient(circle,#fff 1px,transparent 2px);background-size:58px 58px;animation:drift 14s linear infinite}.scene.shooting_stars:after{background:linear-gradient(120deg,transparent 47%,#fff 49%,transparent 51%);background-size:280px 280px;animation:shoot 5s linear infinite}.scene.rose_petals:before{content:"🌹  💗  🌸  ❤️  🌹  💕";font-size:42px;word-spacing:70px;animation:falling 10s linear infinite}.scene.neon_hearts:before{content:"❤  ♥  ♡  ❤  ♥  ♡";font-size:80px;color:#ff5fb4;filter:drop-shadow(0 0 18px #ff4fd8);animation:pulse 3s ease-in-out infinite}.scene.romantic_sky:before{background:radial-gradient(circle,#fff 1px,transparent 2px);background-size:45px 45px;animation:drift 18s linear infinite}.scene.golden_sparkles:before{background:radial-gradient(circle,#ffd36a 1px,transparent 3px);background-size:45px 45px;animation:twinklebg 2s ease-in-out infinite alternate}.scene.polaroid_glow:before{background:linear-gradient(25deg,transparent 40%,#fff2 41% 48%,transparent 49%),linear-gradient(140deg,transparent 35%,#fff1 36% 48%,transparent 49%);background-size:260px 220px;animation:drift 20s linear infinite}.scene.bubbles:before{background:radial-gradient(circle at 20% 20%,#fff4 0 7px,transparent 8px),radial-gradient(circle at 70% 50%,#7fe8ff4a 0 13px,transparent 14px),radial-gradient(circle at 40% 80%,#fff3 0 9px,transparent 10px);background-size:140px 160px;animation:floatScene 9s linear infinite}.scene.confetti_party:before{background:linear-gradient(45deg,#ff4f9c 0 4px,transparent 4px 20px),linear-gradient(135deg,#ffd166 0 4px,transparent 4px 22px),linear-gradient(70deg,#72e7ff 0 4px,transparent 4px 24px);background-size:60px 70px;animation:drift 8s linear infinite}.scene.fireworks:before{background:radial-gradient(circle at 20% 25%,#fff 0 2px,transparent 3px),radial-gradient(circle at 75% 35%,#ffcf66 0 2px,transparent 3px),radial-gradient(circle at 45% 70%,#ff4fc4 0 2px,transparent 3px);background-size:160px 160px;animation:twinklebg 1.6s ease-in-out infinite alternate}.scene.mystic_fog:before{background:radial-gradient(ellipse at 30% 40%,#c786ff66,transparent 38%),radial-gradient(ellipse at 70% 65%,#7dffe144,transparent 40%);filter:blur(30px);animation:fog 10s ease-in-out infinite alternate}.scene.magic_portal:before{border:8px solid #7dffe188;border-radius:50%;width:52vmin;height:52vmin;inset:24vh auto auto 24vw;box-shadow:0 0 70px #7dffe1, inset 0 0 50px #7dffe1;animation:spin 12s linear infinite}.scene.lanterns:before{content:"🏮   🏮   🏮   🏮   🏮";font-size:58px;word-spacing:90px;animation:floatScene 7s ease-in-out infinite}.scene.fairy_lights:before{background:radial-gradient(circle,#ffe36e 0 5px,transparent 7px);background-size:80px 80px;filter:drop-shadow(0 0 10px #ffe36e);animation:twinklebg 1.5s ease-in-out infinite alternate}.scene.cinematic_aurora:before{background:linear-gradient(120deg,transparent 20%,#9f7cff55 40%,#7dffe155 55%,transparent 75%);filter:blur(40px);animation:aurora 8s ease-in-out infinite alternate}.scene.balloons:before{content:"🎈   🎈   🎈   🎈";font-size:72px;word-spacing:110px;animation:floatScene 8s ease-in-out infinite}.scene.party:before{content:"✨ 🎉 🎊 ✨ 🎉 🎊";font-size:55px;word-spacing:70px;animation:falling 7s linear infinite}.scene.flower_petals:before{content:"🌸  🌷  🌺  💮  🌼  🌸";font-size:48px;word-spacing:58px;animation:falling 11s linear infinite}.scene.cherry_blossoms:before{content:"🌸  ✿  🌸  ✿  🌸";font-size:58px;word-spacing:72px;animation:falling 12s linear infinite}.scene.butterflies:before{content:"🦋   🦋   🦋   🦋";font-size:58px;word-spacing:90px;animation:floatScene 8s ease-in-out infinite}.scene.candy_bubbles:before{content:"🍭  🫧  🍬  🫧  🍭";font-size:48px;word-spacing:50px;animation:floatScene 7s ease-in-out infinite}.scene.sunrise_glow:before{background:radial-gradient(circle at 50% 100%,#fff4a8 0 4%,#ff9d66 12%,transparent 45%);animation:pulse 6s ease-in-out infinite}.scene.candle_glow:before{background:radial-gradient(circle at 25% 75%,#ffd37a 0 2%,#ff9a4a66 7%,transparent 20%),radial-gradient(circle at 75% 75%,#ffd37a 0 2%,#ff9a4a66 7%,transparent 20%);animation:twinklebg 2s infinite alternate}.scene.ocean_waves:before{background:repeating-radial-gradient(ellipse at 50% 110%,#ffffff22 0 2px,transparent 3px 35px);animation:drift 12s linear infinite}.scene.city_glow:before{background:linear-gradient(90deg,transparent 0 8%,#ffffff18 8% 11%,transparent 11% 18%,#ffffff10 18% 23%,transparent 23% 100%);background-size:120px 100%;animation:drift 18s linear infinite}.scene.retro_grid:before{background:linear-gradient(#67e8f933 1px,transparent 1px),linear-gradient(90deg,#67e8f933 1px,transparent 1px);background-size:44px 44px;transform:perspective(500px) rotateX(60deg);transform-origin:bottom}.scene.spotlights:before{background:conic-gradient(from 210deg at 50% 100%,transparent 0 20deg,#fff2a622 21deg 35deg,transparent 36deg 70deg,#fff2a622 71deg 85deg,transparent 86deg);animation:pulse 4s infinite}.scene.gift_ribbons:before{background:linear-gradient(45deg,transparent 43%,#fff3 44% 48%,transparent 49%),linear-gradient(-45deg,transparent 43%,#ff8fb955 44% 48%,transparent 49%);background-size:120px 120px;animation:drift 10s linear infinite}.scene.color_splash:before{background:radial-gradient(circle at 15% 30%,#ff4f8b55 0 8%,transparent 20%),radial-gradient(circle at 80% 25%,#ffcc4d66 0 8%,transparent 20%),radial-gradient(circle at 45% 70%,#4ad7c566 0 10%,transparent 23%);animation:pulse 5s ease-in-out infinite}.scene.fireflies:before{background:radial-gradient(circle,#eaff78 0 2px,transparent 3px);background-size:90px 90px;filter:drop-shadow(0 0 7px #eaff78);animation:drift 14s linear infinite}.scene.silk_glow:before{background:linear-gradient(120deg,transparent 25%,#ffd0df22 40%,#fff3 50%,#ffd0df22 60%,transparent 75%);filter:blur(18px);animation:aurora 9s ease-in-out infinite alternate}.scene.floating_clouds:before{content:"☁️       ☁️          ☁️";font-size:90px;opacity:.45;animation:drift 20s linear infinite}.scene.marble_glow:before{background:repeating-linear-gradient(125deg,transparent 0 28px,#fff1 30px 34px,transparent 36px 75px);animation:drift 25s linear infinite}@keyframes shoot{to{transform:translate(-35%,45%)}}@keyframes falling{to{transform:translateY(130vh) rotate(25deg)}}@keyframes pulse{50%{transform:scale(1.08);opacity:.4}}@keyframes twinklebg{to{opacity:.25;transform:scale(1.04)}}@keyframes floatScene{50%{transform:translateY(-12vh) translateX(3vw)}}@keyframes fog{to{transform:translateX(10%) scale(1.15);opacity:.35}}@keyframes spin{to{transform:rotate(360deg)}}@keyframes aurora{to{transform:translateX(8%) skewX(-8deg) scale(1.15)}}.page-garden .screen.active{padding:50px 20px;background:radial-gradient(circle at 50% 30%,#ffffff22,transparent 45%)}.page-garden .btn{border-radius:14px;background:linear-gradient(135deg,#fff,#ffd7e8);color:#7a234c}.page-garden .option{border-radius:22px;backdrop-filter:blur(14px)}.page-garden .paper{border-radius:45% 55% 42% 58%/55% 42% 58% 45%}.page-party .btn{border-radius:10px;transform:rotate(-1deg);background:var(--accent);color:#25101f}.page-party .option{border-radius:12px;border:2px dashed #fff8}.page-party .emoji{filter:drop-shadow(8px 10px 0 #0003)}.page-envelope .screen{align-items:center}.page-envelope .paper{position:relative;border-radius:4px;box-shadow:0 0 0 12px #f6e6d6,0 25px 80px #0008}.page-envelope .btn{border-radius:4px;background:#8f2448;color:#fff;letter-spacing:.08em}.page-envelope .gift{font-size:120px}.page-scrapbook .screen{background:rgba(255,255,255,.06);margin:18px;border-radius:34px;min-height:calc(100svh - 36px)}.page-scrapbook .photo{border-radius:3px;padding:12px 12px 34px;background:#fff}.page-scrapbook .btn{border-radius:0;background:#fff;color:#333;box-shadow:6px 6px 0 #0003}.page-postcard .screen{justify-content:flex-end;padding-bottom:10vh}.page-postcard .lead{background:#0004;padding:18px;border-radius:18px;backdrop-filter:blur(10px)}.page-postcard .btn{border-radius:999px;background:transparent;color:#fff;border:2px solid #fff}.page-luxury .screen{background:linear-gradient(135deg,#0005,transparent,#0005)}.page-luxury h1,.page-luxury h2{font-family:Georgia,serif;letter-spacing:.04em}.page-luxury .btn{border-radius:2px;background:linear-gradient(135deg,#fff7d6,#c79b3b);color:#1d1405;text-transform:uppercase;letter-spacing:.14em}.page-neon .screen{background:#05000a88}.page-neon .btn{background:#0b0614;color:#fff;border:2px solid var(--accent);box-shadow:0 0 12px var(--accent),0 0 35px #000}.page-neon h1,.page-neon h2{text-shadow:0 0 18px var(--accent)}.page-arcade .screen{font-family:monospace;background:linear-gradient(#0c0022cc,#001c2acc)}.page-arcade .btn,.page-arcade .option{border-radius:0;text-transform:uppercase;box-shadow:5px 5px 0 #000;border:2px solid var(--accent)}.page-mystery .screen{background:radial-gradient(circle at 50% 50%,#ffffff0b,transparent 55%)}.page-mystery .btn{border-radius:0;background:#111;color:#fff;border:1px solid #ffffff55}.page-portal .screen{background:radial-gradient(circle at center,#7dffe11f,transparent 45%)}.page-portal .btn{border-radius:50%;width:150px;height:150px;padding:10px;background:transparent;color:#fff;border:3px solid var(--accent);box-shadow:0 0 35px var(--accent),inset 0 0 25px var(--accent)}.page-stage .screen{background:linear-gradient(90deg,#0008,transparent,#0008)}.page-stage .btn{border-radius:6px;background:#fff;color:#111;text-transform:uppercase}.page-lantern .screen{background:linear-gradient(#0004,#0008)}.page-lantern .btn{border-radius:999px;background:#9b2e18;color:#ffe6aa;border:1px solid #ffe6aa}.page-cinematic .screen{background:linear-gradient(180deg,#0003,transparent,#0008)}.page-cinematic .btn{border-radius:999px;background:linear-gradient(135deg,#fff,var(--accent));color:#17111b}.page-cinematic .paper{border-radius:28px 4px 28px 4px}@media(max-width:600px){.option{width:calc(100% - 16px);margin:5px}}</style></head><body class="page-__PAGE_STYLE__">__BANNER__<div class="scene __SCENE__"></div><div class="confetti"></div><main>
<section class="screen active" id="intro"><div class="emoji">__EMOJI__</div><p class="eyebrow">a premium __CATEGORY__ story</p><h1>__TITLE__</h1><p class="lead">__NAME__, are you ready for a little surprise?</p><button class="btn opening-__OPENING__" onclick="go('choices')">__OPENING_LABEL__</button></section>
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
        "__SCENE__": scene, "__PAGE_STYLE__": page_style, "__OPENING__": site.get("opening_style", page_style), "__OPENING_LABEL__": {"envelope":"OPEN THE LETTER 💌","gift":"OPEN THE GIFT 🎁","flower":"LET IT BLOOM 🌸","cinematic":"START THE STORY ✨","portal":"ENTER THE PORTAL 🪄","luxury":"BEGIN THE EXPERIENCE 👑","neon":"TAP TO IGNITE ⚡","arcade":"PRESS START ▶","elegant":"OPEN YOUR WISH ✨"}.get(site.get("opening_style", page_style), "START THE STORY ✨")
    }
    for key, value in replacements.items():
        html = html.replace(key, value)
    return HTMLResponse(html)


# ===================== WISH EXPERIENCE 2.0 =====================
async def _public_site_for_api(slug: str):
    site = await db.websites.find_one({"slug": slug})
    if not site:
        raise HTTPException(404, "Website not found")
    if not site.get("published"):
        raise HTTPException(404, "Website not published")
    if not site.get("is_permanent"):
        expires = as_utc(site.get("published_expires_at"))
        if not expires or expires <= datetime.now(timezone.utc):
            raise HTTPException(410, "This website has expired")
    return site

@app.post("/api/site/{slug}/event")
async def experience_event(slug: str, request: Request):
    site = await _public_site_for_api(slug)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    event = str(payload.get("event", "interaction"))[:40].replace(".", "_").replace("$", "_")
    visitor = str(payload.get("visitor_id", ""))[:80]
    allowed = {"experience_opened", "chapter_intro", "chapter_choices", "chapter_reveal", "chapter_letter", "chapter_memories", "chapter_video", "chapter_finale", "surprise_opened", "letter_opened", "finale_unlocked", "shared", "fullscreen", "photo_opened", "guestbook_sent"}
    if event not in allowed:
        event = "interaction"
    update = {"$inc": {f"event_counts.{event}": 1}, "$set": {"last_interaction_at": datetime.now(timezone.utc)}}
    if visitor:
        update["$set"]["last_visitor_id"] = visitor
    await db.websites.update_one({"_id": site["_id"]}, update)
    return {"ok": True}

@app.post("/api/site/{slug}/reaction")
async def experience_reaction(slug: str, request: Request):
    site = await _public_site_for_api(slug)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    reaction = str(payload.get("reaction", "❤️"))
    reaction_map = {"❤️":"heart", "🥹":"tears", "🎉":"party", "✨":"sparkle", "😍":"love"}
    key = reaction_map.get(reaction, "heart")
    await db.websites.update_one({"_id": site["_id"]}, {"$inc": {f"reaction_counts.{key}": 1}, "$set": {"last_reaction_at": datetime.now(timezone.utc)}})
    return {"ok": True, "reaction": reaction}

@app.post("/api/site/{slug}/guestbook")
async def experience_guestbook(slug: str, request: Request):
    site = await _public_site_for_api(slug)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    name = str(payload.get("name", "")).strip()[:40]
    message = str(payload.get("message", "")).strip()[:300]
    visitor = str(payload.get("visitor_id", "")).strip()[:80]
    if not name or not message:
        raise HTTPException(400, "Name and message are required")
    now = datetime.now(timezone.utc)
    if visitor:
        recent = await db.guestbook.find_one({"slug": slug, "visitor_id": visitor, "created_at": {"$gte": now - timedelta(minutes=2)}})
        if recent:
            raise HTTPException(429, "Please wait before sending another message")
    await db.guestbook.insert_one({"slug": slug, "website_id": site["_id"], "name": name, "message": message, "visitor_id": visitor or None, "created_at": now})
    await db.websites.update_one({"_id": site["_id"]}, {"$inc": {"guestbook_count": 1}, "$set": {"last_guestbook_at": now}})
    return {"ok": True}

@app.get("/api/site/{slug}/public-stats")
async def public_stats(slug: str):
    site = await _public_site_for_api(slug)
    return {"ok": True, "views": int(site.get("views", 0) or 0), "reactions": site.get("reaction_counts", {}), "guestbook": int(site.get("guestbook_count", 0) or 0)}

def render_premium_story(site, preview=False, preview_token=None):
    """Experience 2.0 compatibility layer over the existing premium renderer."""
    response = render_premium_story_legacy(site, preview, preview_token)
    html = response.body.decode("utf-8")
    slug = escape(str(site.get("slug", "")))
    api_enabled = "false" if preview else "true"
    guestbook_enabled = "true" if "guestbook" in set(site.get("extras", [])) else "false"
    recipient = escape(str(site.get("recipient_name") or "You"))
    gate_cfg = PREMIUM_THEME_CONFIG.get(site.get("premium_theme") or site.get("theme"), {})
    gate_icon = escape(str(gate_cfg.get("emoji") or "✨"))
    overlay = f"""<style>
#wx-gate{{position:fixed;inset:0;z-index:99999;display:grid;place-items:center;background:radial-gradient(circle at 50% 35%,var(--accent,#ff8fb9),transparent 28%),#070510;transition:opacity .7s ease,visibility .7s}}
#wx-gate.hide{{opacity:0;visibility:hidden;pointer-events:none}}
.wx-gate-card{{width:min(560px,90vw);padding:42px 28px;text-align:center;border:1px solid #ffffff28;border-radius:32px;background:#ffffff10;backdrop-filter:blur(24px);box-shadow:0 30px 100px #0009}}
.wx-gate-card .wx-orb{{font-size:72px;filter:drop-shadow(0 0 30px var(--accent,#ff8fb9));animation:wxPulse 2.4s ease-in-out infinite}}
.wx-gate-card h2{{margin:8px 0;font-size:clamp(28px,7vw,52px)}} .wx-gate-card p{{opacity:.75;line-height:1.7}}
#wx-song{{position:fixed;width:1px;height:1px;left:-10000px;top:-10000px;opacity:.01;pointer-events:none}}
#wx-music{{position:fixed;left:14px;bottom:14px;z-index:9997;border:1px solid #ffffff2a;border-radius:999px;padding:11px 14px;background:#090711b8;color:#fff;backdrop-filter:blur(14px);cursor:pointer;font-weight:800;box-shadow:0 8px 30px #0005}}
#wx-enter{{border:0;border-radius:999px;padding:16px 28px;font-weight:900;font-size:16px;cursor:pointer;background:linear-gradient(135deg,#fff,var(--accent,#ff8fb9));color:#151018;box-shadow:0 15px 45px #0006}}
@keyframes wxPulse{{50%{{transform:scale(1.08) rotate(3deg)}}}}
#wx-progress{{position:fixed;z-index:9998;top:0;left:0;width:100%;height:4px;background:#ffffff18;pointer-events:none}} #wx-progress span{{display:block;width:0;height:100%;background:var(--accent,#ff8fb9);box-shadow:0 0 15px var(--accent,#ff8fb9);transition:width .35s ease}}
#wx-tools{{position:fixed;right:14px;bottom:14px;z-index:9997;display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}} .wx-tool{{border:1px solid #ffffff2a;border-radius:999px;padding:11px 14px;background:#090711b8;color:#fff;backdrop-filter:blur(14px);cursor:pointer;font-weight:800;box-shadow:0 8px 30px #0005}}
#wx-toast{{position:fixed;left:50%;bottom:76px;transform:translate(-50%,20px);z-index:10000;padding:12px 17px;border-radius:999px;background:#090711e8;border:1px solid #ffffff24;opacity:0;pointer-events:none;transition:.3s;white-space:nowrap}} #wx-toast.show{{opacity:1;transform:translate(-50%,0)}}
.wx-lightbox{{position:fixed;inset:0;z-index:10001;display:none;place-items:center;background:#000d;padding:20px}} .wx-lightbox.open{{display:grid}} .wx-lightbox img{{max-width:94vw;max-height:88vh;border-radius:22px;box-shadow:0 30px 100px #000}} .wx-lightbox button{{position:absolute;top:18px;right:18px;border:0;border-radius:50%;width:46px;height:46px;font-size:22px;cursor:pointer}}
.wx-spark{{position:fixed;width:5px;height:5px;border-radius:50%;background:#fff;box-shadow:0 0 15px var(--accent,#fff);z-index:9996;pointer-events:none;animation:wxSpark .8s ease-out forwards}} @keyframes wxSpark{{to{{transform:translate(var(--dx),var(--dy)) scale(0);opacity:0}}}}
@media(prefers-reduced-motion:reduce){{*,*::before,*::after{{animation-duration:.01ms!important;animation-iteration-count:1!important;scroll-behavior:auto!important}}}}
</style>
<div id="wx-gate"><div class="wx-gate-card"><div class="wx-orb">{gate_icon}</div><div style="letter-spacing:.16em;text-transform:uppercase;font-size:11px;opacity:.65">A PRIVATE MOMENT FOR</div><h2>{recipient}</h2><p>This isn't just a webpage. It's a little experience made especially for you.</p><button id="wx-enter">ENTER THE EXPERIENCE ✨</button></div></div>
<div id="wx-progress"><span></span></div><button class="wx-tool" id="wx-music" style="display:none">🎵 Music: ON</button><div id="wx-tools"><button class="wx-tool" id="wx-share">↗ Share</button><button class="wx-tool" id="wx-full">⛶ Fullscreen</button><button class="wx-tool" id="wx-replay">↻ Replay</button></div>
<div id="wx-toast"></div><div class="wx-lightbox" id="wx-lightbox"><button id="wx-close">×</button><img id="wx-lightbox-img" alt="Memory"></div>
<script>
(()=>{{const slug='{slug}',apiEnabled={api_enabled},guestbookEnabled={guestbook_enabled};
const visitor=(localStorage.getItem('wish_visitor')||((crypto.randomUUID)?crypto.randomUUID():String(Date.now())+Math.random()));localStorage.setItem('wish_visitor',visitor);
const gate=document.getElementById('wx-gate'),toast=document.getElementById('wx-toast'),bar=document.querySelector('#wx-progress span'),screens=[...document.querySelectorAll('.screen')];
function toastMsg(t){{toast.textContent=t;toast.classList.add('show');clearTimeout(window.__wt);window.__wt=setTimeout(()=>toast.classList.remove('show'),2200)}}
function event(name){{if(!apiEnabled)return;fetch('/api/site/'+slug+'/event',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{event:name,visitor_id:visitor}})}}).catch(()=>{{}})}}
function track(){{const active=document.querySelector('.screen.active');if(!active)return;const i=Math.max(0,screens.indexOf(active));bar.style.width=((i+1)/Math.max(1,screens.length)*100)+'%';event('chapter_'+active.id)}}
function spark(x,y){{for(let i=0;i<7;i++){{const e=document.createElement('i');e.className='wx-spark';e.style.left=x+'px';e.style.top=y+'px';e.style.setProperty('--dx',(Math.random()*90-45)+'px');e.style.setProperty('--dy',(Math.random()*90-45)+'px');document.body.appendChild(e);setTimeout(()=>e.remove(),900)}}}}
const song=document.getElementById('wx-song'),musicBtn=document.getElementById('wx-music');
let songStarted=false;
async function startSong(withSound=false){{if(!song)return false;try{{if(song.readyState===0){{song.load();}}song.muted=!withSound;const p=song.play();if(p)await p;if(withSound){{song.muted=false;}}songStarted=true;musicBtn.style.display='block';musicBtn.textContent=withSound?'🎵 Music: ON':'🔇 Music: TAP TO UNMUTE';return true}}catch(e){{musicBtn.style.display='block';musicBtn.textContent='🎵 Tap to Play';return false}}}}
if(song){{
  song.volume=0.85;
  song.addEventListener('error',()=>{{musicBtn.style.display='block';musicBtn.textContent='⚠️ Music unavailable'}});
  musicBtn.onclick=async()=>{{if(song.paused){{await startSong(true)}}else{{song.pause();musicBtn.textContent='🔇 Music: OFF'}}}};
  // Prime muted playback where the browser permits it, but never reload the
  // element after the user's gesture because that can interrupt playback.
  startSong(false);
}}
const enterExperience=document.getElementById('wx-enter');
enterExperience.addEventListener('pointerdown',()=>{{if(song && song.paused){{startSong(true)}}}},{{passive:true}});
enterExperience.onclick=async()=>{{gate.classList.add('hide');if(song){{const ok=await startSong(true);if(!ok){{musicBtn.style.display='block';musicBtn.textContent='🎵 Tap to Play'}}}}event('experience_opened');track();toastMsg('✨ Experience unlocked')}};
document.getElementById('wx-replay').onclick=()=>location.reload();
document.getElementById('wx-full').onclick=()=>{{document.documentElement.requestFullscreen?.();event('fullscreen')}};
document.getElementById('wx-share').onclick=async()=>{{try{{if(navigator.share){{await navigator.share({{title:document.title,text:'A special wish was made for you ✨',url:location.href}})}}else{{await navigator.clipboard.writeText(location.href)}}event('shared');toastMsg('🔗 Share link ready')}}catch(e){{}}}};
document.addEventListener('click',e=>{{spark(e.clientX,e.clientY);if(e.target.closest('.btn,.option,.interactive-card'))setTimeout(track,60)}});
const imgs=[...document.querySelectorAll('.gallery img,.gallery-grid img,.photo img')],lb=document.getElementById('wx-lightbox'),lbi=document.getElementById('wx-lightbox-img');imgs.forEach(img=>img.addEventListener('click',()=>{{lbi.src=img.src;lb.classList.add('open');event('photo_opened')}}));document.getElementById('wx-close').onclick=()=>lb.classList.remove('open');lb.onclick=e=>{{if(e.target===lb)lb.classList.remove('open')}};window.addEventListener('keydown',e=>{{if(e.key==='Escape')lb.classList.remove('open')}});
setTimeout(()=>{{
  if(window.reactSite){{const oldReact=window.reactSite;window.reactSite=async(r)=>{{if(apiEnabled)fetch('/api/site/'+slug+'/reaction',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{reaction:r,visitor_id:visitor}})}}).catch(()=>{{}});oldReact(r);}}}}
  if(guestbookEnabled && window.sendGuestbook){{window.sendGuestbook=async()=>{{const n=document.getElementById('guestname')?.value.trim(),m=document.getElementById('guestmessage')?.value.trim(),status=document.getElementById('gueststatus');if(!n||!m){{if(status)status.textContent='Please write your name and message first.';return}}if(!apiEnabled){{if(status)status.textContent='Preview mode: guestbook is disabled.';return}}try{{const r=await fetch('/api/site/'+slug+'/guestbook',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{name:n,message:m,visitor_id:visitor}})}});const data=await r.json().catch(()=>({{}}));if(!r.ok)throw new Error(data.detail||'Unable to save');if(status)status.textContent='✨ Your beautiful message was saved!';event('guestbook_sent')}}catch(err){{if(status)status.textContent='⚠️ '+err.message}}}}}}
}},0);
}})();
</script>"""
    html = html.replace("<body>", "<body>" + overlay, 1)
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

    preview_banner = "<div class='preview-banner'>🔒 PRIVATE 30-SECOND PREVIEW — NOT PUBLISHED</div>" if preview else ""
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

    # Advanced interactive modules
    advanced_html = ""
    if "countdown" in extras:
        advanced_html += "<section class='advanced-module'><h2>⏳ The Moment Is Coming</h2><div id='countdown' class='countdown'>Loading...</div></section>"
    if "timeline" in extras:
        advanced_html += "<section class='advanced-module'><h2>🕰 Our Beautiful Story</h2><div class='timeline'><div>✨ The beginning of something special</div><div>📸 Memories we will never forget</div><div>💖 Today — another beautiful chapter</div><div>🌟 The future is still waiting</div></div></section>"
    if "lovemeter" in extras:
        advanced_html += "<section class='advanced-module'><h2>💞 Love Meter</h2><button class='meter-btn' onclick='fillLove()'>Check the Magic 💖</button><div class='lovebar'><span id='lovefill'></span></div><div id='lovevalue'></div></section>"
    if "reactions" in extras:
        advanced_html += '''<section class='advanced-module'><h2>👏 Send a Reaction</h2><div class='reaction-row'><button onclick="reactSite('❤️')">❤️</button><button onclick="reactSite('🥹')">🥹</button><button onclick="reactSite('🎉')">🎉</button><button onclick="reactSite('✨')">✨</button><button onclick="reactSite('😍')">😍</button></div><div id='reactionstatus'></div></section>'''
    if "guestbook" in extras:
        advanced_html += "<section class='advanced-module'><h2>💬 Leave a Memory</h2><div class='guestbook'><input id='guestname' maxlength='40' placeholder='Your name'><textarea id='guestmessage' maxlength='300' placeholder='Write something beautiful...'></textarea><button onclick='sendGuestbook()'>Send Message ✨</button><div id='gueststatus'></div></div></section>"

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
.cinematic-final{{margin-top:30px;padding:42px 20px;border-radius:28px;text-align:center;background:linear-gradient(135deg,rgba(255,255,255,.12),rgba(255,255,255,.03))}}.advanced-module{{margin:30px auto 0;max-width:760px;padding:28px;border-radius:26px;background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.18);backdrop-filter:blur(14px);text-align:center}}.advanced-module h2{{font-size:clamp(24px,5vw,40px)}}.countdown{{font-size:clamp(28px,7vw,64px);font-weight:900;color:var(--accent);letter-spacing:.05em}}.timeline{{display:grid;gap:12px;text-align:left}}.timeline div{{padding:18px;border-left:3px solid var(--accent);background:rgba(255,255,255,.07);border-radius:12px}}.reaction-row{{display:flex;justify-content:center;gap:10px;flex-wrap:wrap}}.reaction-row button,.guestbook button,.meter-btn{{border:0;border-radius:18px;padding:13px 18px;font-weight:900;font-size:20px;cursor:pointer;background:rgba(255,255,255,.92)}}.guestbook{{display:grid;gap:10px}}.guestbook input,.guestbook textarea{{width:100%;border:1px solid rgba(255,255,255,.2);border-radius:16px;padding:14px;background:rgba(0,0,0,.18);color:#fff;font:inherit}}.lovebar{{height:24px;border-radius:999px;background:rgba(255,255,255,.12);overflow:hidden;margin-top:18px}}.lovebar span{{display:block;width:0;height:100%;background:linear-gradient(90deg,#ff4f9a,var(--accent));transition:width 1.2s ease}}
</style>
</head><body>
{preview_banner}{particles}{stars}{hearts}{lanterns}{rain}{fireworks}
{song_html}
<div class='wrap'><main class='card'>{recipient}<h1>{title}</h1><div class='message'>{message}</div>{photo_html}{video_html}{surprise_html}<div class='badge'>✨ Created with WishVerse ✨</div></main></div>
<script>function revealSurprise(b){{b.parentElement.classList.toggle('open');b.textContent=b.parentElement.classList.contains('open')?'✨ Surprise Revealed!':'🎁 Click Here to Reveal Your Surprise'}}function openLetter(b){{b.parentElement.classList.toggle('open');b.textContent=b.parentElement.classList.contains('open')?'💖 Letter Opened':'💌 Open My Secret Letter'}}function celebrate(){{for(let i=0;i<90;i++){{let e=document.createElement('i');e.className='confetti-piece';e.style.left=Math.random()*100+'vw';e.style.transform='rotate('+Math.random()*360+'deg)';e.style.animationDelay=Math.random()*0.7+'s';e.style.background='hsl('+Math.random()*360+' 90% 65%)';document.body.appendChild(e);setTimeout(()=>e.remove(),4500)}}}}function fillLove(){{const v=88+Math.floor(Math.random()*13);document.getElementById('lovefill').style.width=v+'%';document.getElementById('lovevalue').textContent=v+'% magical 💖'}}async function reactSite(e){{document.getElementById('reactionstatus').textContent='Thanks for reacting '+e}}async function sendGuestbook(){{const n=document.getElementById('guestname').value.trim(),m=document.getElementById('guestmessage').value.trim();document.getElementById('gueststatus').textContent=n&&m?'✨ Your beautiful message was saved!':'Please write your name and message first.'}}const cd=document.getElementById('countdown');if(cd){{let target=Date.now()+24*60*60*1000;setInterval(()=>{{let d=Math.max(0,target-Date.now()),h=Math.floor(d/36e5),mi=Math.floor(d%36e5/6e4),se=Math.floor(d%6e4/1e3);cd.textContent=`${{h}}h ${{mi}}m ${{se}}s`}},1000)}}</script>
{premium_html}{advanced_html}

</body></html>""")

@app.get("/s/{slug}", response_class=HTMLResponse)
async def public_website(slug: str):
    site = await authorized_site(slug)
    await db.websites.update_one({"_id": site["_id"]}, {"$inc": {"views": 1}, "$set": {"last_viewed_at": datetime.now(timezone.utc)}})
    site["views"] = int(site.get("views", 0) or 0) + 1
    return render_site(site)

@app.get("/preview/{slug}", response_class=HTMLResponse)
async def preview_website(slug: str, token: str):
    site = await authorized_site(slug, token)
    return render_site(site, preview=True, preview_token=token)
