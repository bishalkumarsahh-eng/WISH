import asyncio
import logging
import secrets
from datetime import datetime, timezone, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
)

from .config import BOT_TOKEN, OWNER_ID, BASE_URL, PREVIEW_MINUTES, LOG_GROUP_ID
from .db import db, setup_indexes
from .themes import THEMES, PREMIUM_THEME_CONFIG

log = logging.getLogger(__name__)
dp = Dispatcher()

def is_owner(uid):
    return bool(OWNER_ID and uid == OWNER_ID)

async def log_event(bot, text):
    if not LOG_GROUP_ID:
        return
    try:
        await bot.send_message(LOG_GROUP_ID, text)
    except Exception:
        log.exception("Failed to send logger message")


def as_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)

SIMPLE_FONTS = {
    "inter": ("✨ Modern Sans", "Inter"),
    "playfair": ("🌹 Elegant Serif", "Playfair Display"),
    "merriweather": ("📖 Classic Story", "Merriweather"),
    "poppins": ("💎 Clean Premium", "Poppins"),
}

PREMIUM_FONTS = {
    **SIMPLE_FONTS,
    "dancing": ("💌 Dancing Script", "Dancing Script"),
    "great_vibes": ("💕 Great Vibes", "Great Vibes"),
    "cinzel": ("👑 Royal Cinzel", "Cinzel"),
    "cormorant": ("🌙 Luxury Cormorant", "Cormorant Garamond"),
    "montserrat": ("⚡ Modern Montserrat", "Montserrat"),
}

SIMPLE_PLANS = {
    "2h": {"stars": 25, "hours": 2, "label": "⚡ 2 Hours"},
    "15h": {"stars": 50, "hours": 15, "label": "🌟 15 Hours"},
    "permanent": {"stars": 100, "hours": None, "label": "👑 Permanent"},
}
PREMIUM_PLANS = {
    "2h": {"stars": 50, "hours": 2, "label": "💎 2 Hours"},
    "15h": {"stars": 100, "hours": 15, "label": "💎 15 Hours"},
    "permanent": {"stars": 200, "hours": None, "label": "👑 Premium Permanent"},
}

def plans_for(site):
    return PREMIUM_PLANS if site.get("package") == "premium" else SIMPLE_PLANS

async def get_owned_site(slug, user_id):
    # Find by slug first so we can distinguish a missing website from an
    # ownership problem and avoid false "Website not found" messages.
    site = await db.websites.find_one({"slug": slug})
    if not site:
        return None, "missing"
    if int(site.get("owner_id", 0)) != int(user_id):
        return None, "forbidden"
    return site, None

def publish_plan_menu(slug, site):
    plans = plans_for(site)
    icon = "💎" if site.get("package") == "premium" else "✨"
    return kb([
        [InlineKeyboardButton(text=f"⚡ {plans['2h']['stars']} ⭐ • 2 Hours", callback_data=f"plan:{slug}:2h")],
        [InlineKeyboardButton(text=f"🌟 {plans['15h']['stars']} ⭐ • 15 Hours", callback_data=f"plan:{slug}:15h")],
        [InlineKeyboardButton(text=f"👑 {plans['permanent']['stars']} ⭐ • Permanent", callback_data=f"plan:{slug}:permanent")],
        [InlineKeyboardButton(text=f"{icon} {site.get('package','simple').title()} Package", callback_data="noop")],
    ])

def category_menu():
    return kb([
        [InlineKeyboardButton(text="🎂 Birthday", callback_data="cat:birthday"), InlineKeyboardButton(text="❤️ Valentine", callback_data="cat:valentine")],
        [InlineKeyboardButton(text="💍 Anniversary", callback_data="cat:anniversary"), InlineKeyboardButton(text="👫 Friendship", callback_data="cat:friendship")],
        [InlineKeyboardButton(text="🎉 Congratulations", callback_data="cat:congratulations"), InlineKeyboardButton(text="🎁 Surprise", callback_data="cat:surprise")],
        [InlineKeyboardButton(text="✨ Festival", callback_data="cat:festival"), InlineKeyboardButton(text="🌟 Custom", callback_data="cat:custom")],
        [InlineKeyboardButton(text="🏠 My Websites", callback_data="mywebsites")]
    ])

def theme_menu(page=0):
    items = list(THEMES.items())
    per = 8
    chunk = items[page*per:(page+1)*per]
    rows = []
    for i in range(0, len(chunk), 2):
        rows.append([InlineKeyboardButton(text=x[1]["name"], callback_data=f"theme:{x[0]}") for x in chunk[i:i+2]])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Previous", callback_data=f"themes:{page-1}"))
    if (page+1)*per < len(items):
        nav.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"themes:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🔙 Categories", callback_data="categories")])
    return kb(rows)

def package_menu():
    return kb([
        [InlineKeyboardButton(text="✨ Normal — Up to 4 Photos", callback_data="package:simple")],
        [InlineKeyboardButton(text="💎 Premium — Photos + Video", callback_data="package:premium")],
    ])

def font_menu(package, kind="title"):
    fonts = PREMIUM_FONTS if package == "premium" else SIMPLE_FONTS
    rows = []
    items = list(fonts.items())
    for i in range(0, len(items), 2):
        rows.append([InlineKeyboardButton(text=v[0], callback_data=f"font:{kind}:{k}") for k, v in items[i:i+2]])
    return kb(rows)

def finish_photos_menu():
    return kb([[InlineKeyboardButton(text="✅ Done Adding Photos", callback_data="media:photos_done")]])

def premium_theme_menu(category):
    items = [(key, value) for key, value in PREMIUM_THEME_CONFIG.items() if value["category"] == category]
    rows = []
    for i in range(0, len(items), 2):
        rows.append([InlineKeyboardButton(text=v["name"], callback_data=f"ptheme:{k}") for k, v in items[i:i+2]])
    rows.append([InlineKeyboardButton(text="🔙 Choose Package", callback_data="categories")])
    return kb(rows)

def normal_extras_menu():
    return kb([
        [InlineKeyboardButton(text="🎁 Reveal Surprise", callback_data="extra:reveal")],
        [InlineKeyboardButton(text="💌 Secret Message", callback_data="extra:letter")],
        [InlineKeyboardButton(text="🎉 Celebration Effect", callback_data="extra:confetti")],
        [InlineKeyboardButton(text="✨ Continue to Photos", callback_data="extra:done")],
    ])

def premium_extras_menu():
    return kb([
        [InlineKeyboardButton(text="🎁 Click to Reveal Surprise", callback_data="extra:reveal")],
        [InlineKeyboardButton(text="💌 Secret Letter", callback_data="extra:letter")],
        [InlineKeyboardButton(text="🎉 Confetti Celebration", callback_data="extra:confetti")],
        [InlineKeyboardButton(text="✨ Finish Extras", callback_data="extra:done")],
    ])

async def get_draft(uid):
    user = await db.users.find_one({"telegram_id": uid}) or {}
    return user.get("draft")

async def save_draft(uid, draft):
    await db.users.update_one({"telegram_id": uid}, {"$set": {"draft": draft}}, upsert=True)

async def create_site_from_draft(message, draft):
    slug = secrets.token_urlsafe(8).replace("-", "").replace("_", "")
    token = secrets.token_urlsafe(24)
    expires = datetime.now(timezone.utc) + timedelta(minutes=PREVIEW_MINUTES)

    site = {
        "slug": slug,
        "preview_token": token,
        "preview_expires_at": expires,
        "owner_id": message.from_user.id,
        "type": draft.get("type"),
        "theme": draft.get("theme", "starry_night"),
        "recipient_name": draft.get("recipient_name", ""),
        "title": draft.get("title", ""),
        "message": draft.get("message", ""),
        "package": draft.get("package", "simple"),
        "title_font": draft.get("title_font", "great_vibes" if draft.get("package") == "premium" else "playfair"),
        "message_font": draft.get("message_font", "inter"),
        "extras": draft.get("extras", []),
        "surprise_text": draft.get("surprise_text", "A special surprise just for you! ✨"),
        "letter_text": draft.get("letter_text", "You mean more to me than words can say. 💖"),
        "photo_file_ids": draft.get("photo_file_ids", []),
        "video_file_id": draft.get("video_file_id"),
        "published": False,
        "created_at": datetime.now(timezone.utc),
    }
    await db.websites.insert_one(site)
    await db.users.update_one({"telegram_id": message.from_user.id}, {"$unset": {"draft": ""}})

    url = f"{BASE_URL}/preview/{slug}?token={token}"
    media_text = (
        "📷 <b>Normal package:</b> up to 4 photos"
        if site["package"] == "simple"
        else f"💎 <b>Premium package:</b> {len(site['photo_file_ids'])} photo(s) + "
             f"{'1 video' if site.get('video_file_id') else 'no video'}"
    )
    await message.answer(
        f"🎉 <b>Your professional website is ready!</b>\n\n"
        f"{media_text}\n"
        f"🔤 Font: <b>{(PREMIUM_FONTS if site['package']=='premium' else SIMPLE_FONTS).get(site.get('title_font', 'inter'), ('Modern','Inter'))[0]}</b>\n\n"
        f"👀 Preview is private and expires in <b>{PREVIEW_MINUTES} minutes</b>.\n"
        f"🌐 Public sharing unlocks only after publishing.",
        reply_markup=kb([
            [InlineKeyboardButton(text="👀 Preview (2 min)", url=url)],
            [InlineKeyboardButton(text="🚀 Publish Website", callback_data=f"publish:{slug}")]
        ])
    )

@dp.message(CommandStart())
async def start(m):
    await m.answer(
        "✨ <b>Welcome to WishVerse Premium</b>\n\n"
        "Create a professional animated wish website with premium themes, photos, video, and beautiful fonts.\n\n"
        "Choose your occasion:",
        reply_markup=category_menu()
    )

@dp.callback_query(F.data == "noop")
async def noop(c):
    await c.answer()

@dp.callback_query(F.data == "categories")
async def categories(c):
    await c.message.edit_text("🎉 <b>Choose what you want to create</b>", reply_markup=category_menu())
    await c.answer()

@dp.callback_query(F.data.startswith("cat:"))
async def choose_category(c):
    cat = c.data.split(":", 1)[1]
    await save_draft(c.from_user.id, {"type": cat, "step": "package"})
    await c.message.edit_text(
        "📦 <b>Choose how you want to create this website</b>\n\n"
        "✨ <b>Normal</b> — a beautiful single-page wish, up to 4 photos, fonts and interactive extras.\n\n"
        "💎 <b>Premium Story Experience</b> — a full interactive journey like the birthday website you shared: intro → choices → surprise → letter → memories → video → finale.",
        reply_markup=package_menu()
    )
    await c.answer()

@dp.callback_query(F.data.startswith("themes:"))
async def themes_page(c):
    page = int(c.data.split(":", 1)[1])
    await c.message.edit_reply_markup(reply_markup=theme_menu(page))
    await c.answer()

@dp.callback_query(F.data.startswith("ptheme:"))
async def choose_premium_theme(c):
    draft = await get_draft(c.from_user.id)
    if not draft or draft.get("step") != "premium_theme":
        return await c.answer("Please start again.", show_alert=True)
    theme = c.data.split(":", 1)[1]
    info = PREMIUM_THEME_CONFIG.get(theme)
    if not info:
        return await c.answer("Premium theme not found.", show_alert=True)
    draft["premium_theme"] = theme
    draft["theme"] = theme
    draft["step"] = "recipient"
    await save_draft(c.from_user.id, draft)
    await c.message.edit_text(
        f"💎 <b>{info['name']}</b> selected!\n\nYour Premium website will be a complete interactive journey.\n\nNow send the <b>recipient's name</b>, or send <code>skip</code>."
    )
    await c.answer()

@dp.callback_query(F.data.startswith("theme:"))
async def choose_theme(c):
    theme = c.data.split(":", 1)[1]
    if theme not in THEMES:
        return await c.answer("Theme not found", show_alert=True)
    draft = await get_draft(c.from_user.id) or {}
    draft["theme"] = theme
    draft["step"] = "recipient"
    await save_draft(c.from_user.id, draft)
    t = THEMES[theme]
    await c.message.edit_text(
        f"{t['name']} selected!\n\n"
        f"🎭 <b>Style:</b> {t['mode'].title()}\n"
        f"✨ <b>Effects:</b> {t['effect']}\n\n"
        "Now send the <b>recipient's name</b>, or send <code>skip</code>."
    )
    await c.answer()

@dp.callback_query(F.data.startswith("package:"))
async def choose_package(c):
    package = c.data.split(":", 1)[1]
    draft = await get_draft(c.from_user.id)
    if not draft:
        return await c.answer("Please start creating again.", show_alert=True)
    draft["package"] = package
    if package == "simple":
        draft["step"] = "theme"
        await save_draft(c.from_user.id, draft)
        await c.message.edit_text(
            "✨ <b>Normal Website selected</b>\n\nChoose the background theme. After that you will add the name, title, message, fonts and up to 4 photos.",
            reply_markup=theme_menu(0)
        )
    else:
        draft["step"] = "premium_theme"
        await save_draft(c.from_user.id, draft)
        category = draft.get("type", "custom")
        await c.message.edit_text(
            "💎 <b>Premium Story Experience selected</b>\n\nNow choose the complete story theme for your occasion. Every Premium theme uses the interactive multi-screen style inspired by the birthday website you sent.",
            reply_markup=premium_theme_menu(category)
        )
    await c.answer()

@dp.callback_query(F.data.startswith("font:"))
async def choose_font(c):
    _, kind, font = c.data.split(":", 2)
    draft = await get_draft(c.from_user.id)
    if not draft:
        return await c.answer("Please start creating again.", show_alert=True)
    allowed = PREMIUM_FONTS if draft.get("package") == "premium" else SIMPLE_FONTS
    if font not in allowed:
        return await c.answer("This font is not available in your selected package.", show_alert=True)
    if kind == "title":
        draft["title_font"] = font
        draft["step"] = "message_font"
        await save_draft(c.from_user.id, draft)
        await c.message.edit_text("💌 Now choose a DIFFERENT font for the wish/message text:", reply_markup=font_menu(draft.get("package"), "message"))
    else:
        draft["message_font"] = font
        draft["step"] = "extras"
        draft.setdefault("photo_file_ids", [])
        await save_draft(c.from_user.id, draft)
        if draft.get("package") == "premium":
            await c.message.edit_text("💎 Add premium interactive experiences! You can select multiple:", reply_markup=premium_extras_menu())
        else:
            await c.message.edit_text(
                "✨ <b>Add attractive features to your Normal website</b>\n\n"
                "You can include a reveal surprise, secret message and celebration effect. "
                "Then continue to upload up to <b>4 photos</b>.",
                reply_markup=normal_extras_menu()
            )
    await c.answer()

@dp.callback_query(F.data.startswith("extra:"))
async def premium_extra(c):
    choice = c.data.split(":", 1)[1]
    draft = await get_draft(c.from_user.id) or {}
    extras = draft.setdefault("extras", [])
    if choice == "done":
        draft["step"] = "media"
        draft.setdefault("photo_file_ids", [])
        await save_draft(c.from_user.id, draft)
        limit = 8 if draft.get("package") == "premium" else 4
        label = "premium" if draft.get("package") == "premium" else "Normal"
        await c.message.edit_text(
            f"📷 <b>Send your {label} website photos</b>\n\n"
            f"You can send up to <b>{limit} photos</b>. You can also tap Done Adding Photos whenever you finish.",
            reply_markup=finish_photos_menu()
        )
        return await c.answer()
    if choice not in extras:
        extras.append(choice)
    draft["step"] = "extras"
    await save_draft(c.from_user.id, draft)
    if choice == "reveal":
        await c.message.answer("🎁 Send the text that should appear after the visitor clicks <b>Reveal My Surprise</b>.")
        draft["step"] = "surprise_text"
    elif choice == "letter":
        await c.message.answer("💌 Send the secret letter/message that opens when the visitor clicks it.")
        draft["step"] = "letter_text"
    await save_draft(c.from_user.id, draft)
    await c.answer("Added!", show_alert=False)

@dp.callback_query(F.data == "media:photos_done")
async def photos_done(c):
    draft = await get_draft(c.from_user.id)
    if not draft or draft.get("step") != "media":
        return await c.answer("No photo upload is active.", show_alert=True)

    if draft.get("package") == "premium":
        draft["step"] = "video"
        await save_draft(c.from_user.id, draft)
        await c.message.edit_text(
            f"🎬 <b>Premium video section</b>\n\n"
            f"Photos added: <b>{len(draft.get('photo_file_ids', []))}/8</b>\n\n"
            "Now send <b>one video</b>, or send <code>skip</code> to finish without a video."
        )
        return await c.answer()

    await c.answer()
    await create_site_from_draft(c.message, draft)

@dp.callback_query(F.data == "mywebsites")
async def my_websites(c):
    docs = await db.websites.find({"owner_id": c.from_user.id}).sort("created_at", -1).limit(8).to_list(length=8)
    if not docs:
        text = "You have not created any websites yet."
    else:
        lines = ["🏠 <b>Your Websites</b>\n"]
        now = datetime.now(timezone.utc)
        for d in docs:
            live = bool(d.get("published"))
            expires = as_utc(d.get("published_expires_at"))
            if live and not d.get("is_permanent") and expires and expires <= now:
                live = False
            if live:
                if d.get("is_permanent"):
                    status = "👑 LIVE • Permanent"
                else:
                    remaining = max(0, int((expires-now).total_seconds()/60)) if expires else 0
                    status = f"🟢 LIVE • {remaining} min left"
                lines.append(f"{status} • <b>{d.get('title','Untitled')}</b>\n{BASE_URL}/s/{d['slug']}")
            else:
                lines.append(f"🔒 Draft / Expired • <b>{d.get('title','Untitled')}</b>")
        text = "\n\n".join(lines)
    await c.message.edit_text(text, reply_markup=kb([[InlineKeyboardButton(text="➕ Create New", callback_data="categories")]]))
    await c.answer()

@dp.message(F.photo)
async def receive_photo(m):
    draft = await get_draft(m.from_user.id)
    if not draft or draft.get("step") != "media":
        return

    photos = draft.get("photo_file_ids", [])
    limit = 4 if draft.get("package") == "simple" else 8
    if len(photos) >= limit:
        return await m.answer(f"⚠️ This package allows a maximum of {limit} photo(s).")

    photos.append(m.photo[-1].file_id)
    draft["photo_file_ids"] = photos

    await save_draft(m.from_user.id, draft)
    if draft.get("package") == "simple":
        if len(photos) >= 4:
            await m.answer(
                "📷 You reached the 4-photo limit. Your website is ready!",
                reply_markup=finish_photos_menu()
            )
        else:
            await m.answer(
                f"✅ Photo added! <b>{len(photos)}/4</b>\n"
                "Send another photo or tap Done Adding Photos.",
                reply_markup=finish_photos_menu()
            )
    else:
        if len(photos) >= 8:
            draft["step"] = "video"
            await save_draft(m.from_user.id, draft)
            await m.answer("📷 You reached the 8-photo limit.\n\n🎬 Now send one video or send <code>skip</code>.")
        else:
            await m.answer(
                f"✅ Photo added! <b>{len(photos)}/8</b>\n"
                "Send another photo or tap Done Adding Photos.",
                reply_markup=finish_photos_menu()
            )

@dp.message(F.video)
async def receive_video(m):
    draft = await get_draft(m.from_user.id)
    if not draft or draft.get("step") != "video" or draft.get("package") != "premium":
        return
    draft["video_file_id"] = m.video.file_id
    await create_site_from_draft(m, draft)

@dp.message(F.text)
async def collect(m):
    if m.text.startswith("/"):
        return
    draft = await get_draft(m.from_user.id)
    if not draft:
        return

    step = draft.get("step")
    if step == "surprise_text":
        draft["surprise_text"] = m.text[:1500]
        draft["step"] = "extras"
        await save_draft(m.from_user.id, draft)
        return await m.answer("✨ Surprise text saved. Add another premium feature or finish:", reply_markup=premium_extras_menu())

    if step == "letter_text":
        draft["letter_text"] = m.text[:2500]
        draft["step"] = "extras"
        await save_draft(m.from_user.id, draft)
        return await m.answer("💌 Secret letter saved. Add another premium feature or finish:", reply_markup=premium_extras_menu())

    if step == "recipient":
        draft["recipient_name"] = "" if m.text.strip().lower() == "skip" else m.text[:80]
        draft["step"] = "title"
        await save_draft(m.from_user.id, draft)
        return await m.answer("📝 Send the <b>main title</b>. Example: <i>Happy Birthday Ayesha</i>")

    if step == "title":
        draft["title"] = m.text[:120]
        draft["step"] = "message"
        await save_draft(m.from_user.id, draft)
        return await m.answer("💌 Now send the beautiful message or wish.")

    if step == "message":
        draft["message"] = m.text[:5000]
        draft["step"] = "title_font"
        await save_draft(m.from_user.id, draft)
        return await m.answer("🔤 Choose the <b>title font</b> for your website:", reply_markup=font_menu(draft.get("package", "simple"), "title"))

    if step == "media" and m.text.strip().lower() == "skip":
        if draft.get("package") == "simple":
            return await create_site_from_draft(m, draft)
        return await m.answer("Use the <b>Done Adding Photos</b> button to continue to the video step.")

    if step == "video" and m.text.strip().lower() == "skip":
        return await create_site_from_draft(m, draft)

@dp.callback_query(F.data.startswith("publish:"))
async def publish(c, bot):
    slug = c.data.split(":", 1)[1]
    site, site_error = await get_owned_site(slug, c.from_user.id)
    if not site:
        message = "Website not found. It may have been deleted." if site_error == "missing" else "This website belongs to another user."
        return await c.answer(message, show_alert=True)

    now = datetime.now(timezone.utc)
    if site.get("published") and (
        site.get("is_permanent") or
        (site.get("published_expires_at") and as_utc(site["published_expires_at"]) > now)
    ):
        return await c.answer("This website is already live!", show_alert=True)

    user = await db.users.find_one({"telegram_id": c.from_user.id}) or {}
    if is_owner(c.from_user.id) or user.get("free_access"):
        await db.websites.update_one(
            {"_id": site["_id"]},
            {"$set": {
                "published": True,
                "is_permanent": True,
                "publish_plan": "free",
                "published_at": now,
                "published_expires_at": None
            }}
        )
        await c.message.answer(f"👑🎉 <b>Published for FREE — permanently!</b>\n\n🌐 {BASE_URL}/s/{slug}")
        await log_event(bot, f"🆓 <b>FREE PUBLISH</b>\n👤 User: <code>{c.from_user.id}</code>\n🌐 {BASE_URL}/s/{slug}\n📦 Package: {site.get('package', 'simple')}")
        return await c.answer()

    plans = plans_for(site)
    package_name = "💎 Premium" if site.get("package") == "premium" else "✨ Simple"
    await c.message.edit_text(
        f"🚀 <b>{package_name} Publishing</b>\n\n"
        f"⚡ <b>{plans['2h']['stars']} ⭐</b> — Live for 2 hours\n"
        f"🌟 <b>{plans['15h']['stars']} ⭐</b> — Live for 15 hours\n"
        f"👑 <b>{plans['permanent']['stars']} ⭐</b> — Permanent, never expires\n\n"
        "After timed publishing expires, the public link automatically stops working.",
        reply_markup=publish_plan_menu(slug, site)
    )
    await c.answer()

@dp.callback_query(F.data.startswith("plan:"))
async def choose_publish_plan(c, bot):
    _, slug, plan_id = c.data.split(":", 2)
    site, site_error = await get_owned_site(slug, c.from_user.id)
    if not site:
        message = "Website not found. It may have been deleted." if site_error == "missing" else "This website belongs to another user."
        return await c.answer(message, show_alert=True)

    plans = plans_for(site)
    plan = plans.get(plan_id)
    if not plan:
        return await c.answer("Invalid publishing plan.", show_alert=True)

    user = await db.users.find_one({"telegram_id": c.from_user.id}) or {}
    if is_owner(c.from_user.id) or user.get("free_access"):
        await db.websites.update_one(
            {"_id": site["_id"]},
            {"$set": {
                "published": True,
                "is_permanent": True,
                "publish_plan": "free",
                "published_at": datetime.now(timezone.utc),
                "published_expires_at": None
            }}
        )
        await c.message.answer(f"👑🎉 <b>Published for FREE — permanently!</b>\n\n🌐 {BASE_URL}/s/{slug}")
        await log_event(bot, f"🆓 <b>FREE PUBLISH</b>\n👤 User: <code>{c.from_user.id}</code>\n🌐 {BASE_URL}/s/{slug}\n📦 Package: {site.get('package', 'simple')}")
        return await c.answer()

    payload = f"wishverse:{slug}:{c.from_user.id}:{plan_id}:{secrets.token_urlsafe(12)}"
    await db.payments.insert_one({
        "payload": payload,
        "website_slug": slug,
        "user_id": c.from_user.id,
        "amount": plan["stars"],
        "plan": plan_id,
        "package": site.get("package", "simple"),
        "status": "pending",
        "created_at": datetime.now(timezone.utc)
    })

    description = (
        "Keep your WishVerse website live permanently"
        if plan["hours"] is None
        else f"Keep your WishVerse website live for {plan['hours']} hours"
    )
    await bot.send_invoice(
        chat_id=c.from_user.id,
        title=f"WishVerse {site.get('package','simple').title()} • {plan['label']}",
        description=description,
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"{site.get('package','simple').title()} Website Publishing", amount=plan["stars"])]
    )
    await c.answer("Opening Telegram Stars payment...")

@dp.pre_checkout_query()
async def checkout(q, bot):
    p = await db.payments.find_one({"payload": q.invoice_payload, "status": "pending"})
    ok = bool(p and p["user_id"] == q.from_user.id and p["amount"] == q.total_amount)
    await bot.answer_pre_checkout_query(q.id, ok=ok, error_message=None if ok else "Invalid or expired payment.")

@dp.message(F.successful_payment)
async def successful(m):
    info = m.successful_payment
    if await db.payments.find_one({"telegram_payment_charge_id": info.telegram_payment_charge_id}):
        return

    p = await db.payments.find_one({"payload": info.invoice_payload, "status": "pending"})
    if not p or p["user_id"] != m.from_user.id or p["amount"] != info.total_amount:
        log.warning("Invalid successful payment.")
        return

    result = await db.payments.update_one(
        {"_id": p["_id"], "status": "pending"},
        {"$set": {
            "status": "paid",
            "telegram_payment_charge_id": info.telegram_payment_charge_id,
            "provider_payment_charge_id": info.provider_payment_charge_id,
            "paid_at": datetime.now(timezone.utc)
        }}
    )
    if result.modified_count != 1:
        return

    plans = PREMIUM_PLANS if p.get("package") == "premium" else SIMPLE_PLANS
    plan = plans.get(p.get("plan"))
    if not plan:
        return

    now = datetime.now(timezone.utc)
    expires_at = None if plan["hours"] is None else now + timedelta(hours=plan["hours"])
    update_result = await db.websites.update_one(
        {"slug": p["website_slug"], "owner_id": m.from_user.id},
        {"$set": {
            "published": True,
            "is_permanent": plan["hours"] is None,
            "publish_plan": p["plan"],
            "published_at": now,
            "published_expires_at": expires_at
        }}
    )

    if update_result.matched_count != 1:
        log.error("Payment succeeded but website %s was not found for user %s", p["website_slug"], m.from_user.id)
        await m.answer("⚠️ Payment was received, but the website record could not be found. Please contact the bot owner with your payment details.")
        return

    duration = "permanently 👑" if plan["hours"] is None else f"for {plan['hours']} hours ⏳"
    await m.answer(f"🎉 <b>Payment successful — your website is LIVE {duration}!</b>\n\n🌐 {BASE_URL}/s/{p['website_slug']}")
    await log_event(m.bot, f"⭐ <b>PAYMENT SUCCESS</b>\n👤 User: <code>{m.from_user.id}</code>\n📦 Package: {p.get('package', 'simple').title()}\n⭐ Stars: {p['amount']}\n⏳ Plan: {p['plan']}\n🌐 {BASE_URL}/s/{p['website_slug']}")

@dp.message(Command("grantfree"))
async def grantfree(m):
    if not is_owner(m.from_user.id):
        return await m.answer("⛔ Owner only command.")
    parts = m.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        return await m.answer("Usage: /grantfree USER_ID")
    uid = int(parts[1])
    await db.users.update_one({"telegram_id": uid}, {"$set": {"free_access": True}}, upsert=True)
    await m.answer(f"✅ Free permanent publishing granted to <code>{uid}</code>.")
    await log_event(m.bot, f"👑 <b>FREE ACCESS GRANTED</b>\n👤 User ID: <code>{uid}</code>\n🛠 By owner: <code>{m.from_user.id}</code>")

@dp.message(Command("revokefree"))
async def revokefree(m):
    if not is_owner(m.from_user.id):
        return await m.answer("⛔ Owner only command.")
    parts = m.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        return await m.answer("Usage: /revokefree USER_ID")
    uid = int(parts[1])
    await db.users.update_one({"telegram_id": uid}, {"$set": {"free_access": False}}, upsert=True)
    await m.answer(f"❌ Free publishing removed from <code>{uid}</code>.")
    await log_event(m.bot, f"🚫 <b>FREE ACCESS REVOKED</b>\n👤 User ID: <code>{uid}</code>\n🛠 By owner: <code>{m.from_user.id}</code>")

@dp.message(Command("freeusers"))
async def freeusers(m):
    if not is_owner(m.from_user.id):
        return await m.answer("⛔ Owner only command.")
    docs = await db.users.find({"free_access": True}).limit(50).to_list(length=50)
    if not docs:
        return await m.answer("No users currently have free publishing access.")
    text = "👑 <b>Free Publishing Users</b>\n\n" + "\n".join(f"• <code>{d.get('telegram_id')}</code>" for d in docs)
    await m.answer(text)

async def run_bot():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")
    if db is None:
        raise RuntimeError("MONGO_URI is missing")
    if not BASE_URL:
        raise RuntimeError("BASE_URL is missing")

    log.info("🤖 Starting WishVerse bot...")
    await setup_indexes()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        me = await bot.get_me()
        log.info("🤖 Bot authenticated successfully: @%s", me.username)
        log.info("🤖 Polling started.")
        await dp.start_polling(bot, handle_signals=True, close_bot_session=True)
    finally:
        await bot.session.close()
