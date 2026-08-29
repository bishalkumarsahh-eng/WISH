import asyncio
import logging
import secrets
from datetime import datetime, timezone, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
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

def user_log_details(user):
    username = f"@{user.username}" if getattr(user, "username", None) else "No username"
    full_name = (getattr(user, "full_name", None) or "Unknown").replace("<", "&lt;").replace(">", "&gt;")
    return f"👤 Name: <b>{full_name}</b>\n🔗 Username: {username}\n🆔 User ID: <code>{user.id}</code>"


def as_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

async def safe_edit(message, text, reply_markup=None, **kwargs):
    """Edit a Telegram message without crashing on an idempotent edit."""
    try:
        return await message.edit_text(text, reply_markup=reply_markup, **kwargs)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return None
        raise

def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)

def home_menu():
    return kb([
        [InlineKeyboardButton(text="➕ Create a Wish Website", callback_data="categories")],
        [InlineKeyboardButton(text="⚡ Quick Templates", callback_data="templates_menu"), InlineKeyboardButton(text="🧠 Creator Studio", callback_data="studio_menu")],
        [InlineKeyboardButton(text="🏠 My Websites", callback_data="mywebsites"), InlineKeyboardButton(text="📊 Dashboard", callback_data="dashboard_menu")],
        [InlineKeyboardButton(text="🧭 Creation Progress", callback_data="progress_menu"), InlineKeyboardButton(text="📖 Creation Guide", callback_data="guide_menu")],
        [InlineKeyboardButton(text="📚 Ideas & Examples", callback_data="ideas_menu"), InlineKeyboardButton(text="❓ Commands & Help", callback_data="help_menu")],
        [InlineKeyboardButton(text="🧱 Experience Builder", callback_data="v8_builder"), InlineKeyboardButton(text="🚀 Ultra Creator Lab", callback_data="ultra_lab")],
        [InlineKeyboardButton(text="📈 Live Analytics", callback_data="analytics_menu")]
    ])





def studio_menu():
    return kb([
        [InlineKeyboardButton(text="🧩 Start from Template", callback_data="templates_menu"), InlineKeyboardButton(text="🎨 Build from Scratch", callback_data="categories")],
        [InlineKeyboardButton(text="💡 Design Ideas", callback_data="ideas_menu"), InlineKeyboardButton(text="🧭 Creation Guide", callback_data="guide_menu")],
        [InlineKeyboardButton(text="📊 My Dashboard", callback_data="dashboard_menu"), InlineKeyboardButton(text="🏠 My Websites", callback_data="mywebsites")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="home")]
    ])

def ideas_menu():
    return kb([
        [InlineKeyboardButton(text="🎂 Birthday Ideas", callback_data="idea:birthday"), InlineKeyboardButton(text="❤️ Valentine Ideas", callback_data="idea:valentine")],
        [InlineKeyboardButton(text="💍 Anniversary Ideas", callback_data="idea:anniversary"), InlineKeyboardButton(text="🎁 Surprise Ideas", callback_data="idea:surprise")],
        [InlineKeyboardButton(text="🌸 Aesthetic Styles", callback_data="idea:aesthetic"), InlineKeyboardButton(text="🏠 Main Menu", callback_data="home")]
    ])

def template_menu():
    return kb([
        [InlineKeyboardButton(text="🎂 Birthday Luxury", callback_data="template:birthday_luxury"), InlineKeyboardButton(text="❤️ Romantic Valentine", callback_data="template:valentine_romance")],
        [InlineKeyboardButton(text="💍 Anniversary Story", callback_data="template:anniversary_story"), InlineKeyboardButton(text="🎁 Mystery Surprise", callback_data="template:surprise_mystery")],
        [InlineKeyboardButton(text="🌸 Pink Flower Wish", callback_data="template:pink_flower"), InlineKeyboardButton(text="🌌 Night Universe", callback_data="template:night_universe")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="home")]
    ])

TEMPLATE_PRESETS = {
    "birthday_luxury": {"type":"birthday","package":"premium","theme":"birthday_luxury","opening_style":"gift","title_font":"great_vibes","message_font":"cormorant","extras":["reveal","confetti","countdown","timeline"]},
    "valentine_romance": {"type":"valentine","package":"premium","theme":"valentine_rose","opening_style":"envelope","title_font":"great_vibes","message_font":"playfair","extras":["letter","lovemeter","reactions"]},
    "anniversary_story": {"type":"anniversary","package":"premium","theme":"anniversary_luxury","opening_style":"cinematic","title_font":"cinzel","message_font":"cormorant","extras":["timeline","letter","guestbook"]},
    "surprise_mystery": {"type":"surprise","package":"premium","theme":"surprise_magic","opening_style":"portal","title_font":"cinzel","message_font":"inter","extras":["reveal","confetti"]},
    "pink_flower": {"type":"custom","package":"simple","theme":"flower_garden","opening_style":"flower","title_font":"playfair","message_font":"poppins","extras":["reveal","confetti"]},
    "night_universe": {"type":"custom","package":"simple","theme":"starry_night","opening_style":"elegant","title_font":"merriweather","message_font":"inter","extras":["countdown"]},
}

def draft_progress_text(draft):
    if not draft:
        return "🧭 <b>No creation in progress</b>\n\nStart a new website and this screen will show your progress."
    steps=[("type","Occasion"),("package","Package"),("theme","Theme"),("opening_style","Opening"),("recipient_name","Recipient"),("title","Title"),("message","Message"),("title_font","Title Font"),("message_font","Message Font")]
    done=sum(1 for key,_ in steps if draft.get(key))
    return "🧭 <b>Creation Progress</b>\n\n" + "\n".join(f"{'✅' if draft.get(k) else '⬜'} {name}" for k,name in steps) + f"\n\n<b>{done}/{len(steps)} main steps completed</b>\nCurrent step: <code>{draft.get('step','starting')}</code>"
def guide_menu():
    return kb([
        [InlineKeyboardButton(text="1️⃣ Choose Occasion", callback_data="guide:occasion"), InlineKeyboardButton(text="2️⃣ Normal vs Premium", callback_data="guide:package")],
        [InlineKeyboardButton(text="3️⃣ Themes & Entrance", callback_data="guide:theme"), InlineKeyboardButton(text="4️⃣ Text & Fonts", callback_data="guide:text")],
        [InlineKeyboardButton(text="5️⃣ Extras & Media", callback_data="guide:extras"), InlineKeyboardButton(text="6️⃣ Preview & Publish", callback_data="guide:publish")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="home")]
    ])

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
        [InlineKeyboardButton(text="🏠 My Websites", callback_data="mywebsites"), InlineKeyboardButton(text="📊 Dashboard", callback_data="dashboard_menu")],
        [InlineKeyboardButton(text="➕ Create Website", callback_data="categories"), InlineKeyboardButton(text="❓ Help & Guide", callback_data="help_menu")]
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

def opening_style_menu(package):
    if package == "premium":
        return kb([
            [InlineKeyboardButton(text="💌 Envelope Reveal", callback_data="opening:envelope"), InlineKeyboardButton(text="🎁 Gift Box", callback_data="opening:gift")],
            [InlineKeyboardButton(text="🌸 Flower Bloom", callback_data="opening:flower"), InlineKeyboardButton(text="🎬 Cinematic Start", callback_data="opening:cinematic")],
            [InlineKeyboardButton(text="🪄 Magic Portal", callback_data="opening:portal"), InlineKeyboardButton(text="👑 Luxury Entrance", callback_data="opening:luxury")],
            [InlineKeyboardButton(text="⚡ Neon Tap", callback_data="opening:neon"), InlineKeyboardButton(text="🕹 Arcade Start", callback_data="opening:arcade")],
        ])
    return kb([
        [InlineKeyboardButton(text="✨ Elegant Open", callback_data="opening:elegant"), InlineKeyboardButton(text="🎁 Gift Reveal", callback_data="opening:gift")],
        [InlineKeyboardButton(text="💌 Love Letter", callback_data="opening:envelope"), InlineKeyboardButton(text="🌸 Flower Bloom", callback_data="opening:flower")],
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
        [InlineKeyboardButton(text="⏳ Live Countdown", callback_data="extra:countdown")],
        [InlineKeyboardButton(text="✨ Continue to Photos", callback_data="extra:done")],
    ])

def premium_extras_menu():
    return kb([
        [InlineKeyboardButton(text="🎁 Click to Reveal Surprise", callback_data="extra:reveal"), InlineKeyboardButton(text="💌 Secret Letter", callback_data="extra:letter")],
        [InlineKeyboardButton(text="🎉 Confetti Celebration", callback_data="extra:confetti"), InlineKeyboardButton(text="⏳ Live Countdown", callback_data="extra:countdown")],
        [InlineKeyboardButton(text="🕰 Memory Timeline", callback_data="extra:timeline"), InlineKeyboardButton(text="💞 Love Meter", callback_data="extra:lovemeter")],
        [InlineKeyboardButton(text="👏 Reaction Wall", callback_data="extra:reactions"), InlineKeyboardButton(text="💬 Guestbook", callback_data="extra:guestbook")],
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
    # The 2-minute preview countdown starts when the preview link is first opened.
    expires = None

    site = {
        "slug": slug,
        "preview_token": token,
        "preview_expires_at": expires,
        "owner_id": message.from_user.id,
        "type": draft.get("type"),
        "theme": draft.get("theme", "starry_night"),
        "opening_style": draft.get("opening_style", "elegant"),
        "views": 0,
        "recipient_name": draft.get("recipient_name", ""),
        "title": draft.get("title", ""),
        "message": draft.get("message", ""),
        "package": draft.get("package", "simple"),
        "title_font": draft.get("title_font", "great_vibes" if draft.get("package") == "premium" else "playfair"),
        "message_font": draft.get("message_font", "inter"),
        "extras": draft.get("extras", []),
        "event_date": draft.get("event_date"),
        "reactions": {},
        "reaction_counts": {},
        "event_counts": {},
        "guestbook_count": 0,
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
        f"👀 Preview is private and stays active for <b>{PREVIEW_MINUTES} minutes after first opening</b>.\n"
        f"🌐 Public sharing unlocks only after publishing.",
        reply_markup=kb([
            [InlineKeyboardButton(text="👀 Open Preview • 2 min", url=url)],
            [InlineKeyboardButton(text="🚀 Publish Website", callback_data=f"publish:{slug}")]
        ])
    )

@dp.message(CommandStart())
async def start(m):
    await log_event(m.bot, "🚀 <b>BOT STARTED BY USER</b>\n\n" + user_log_details(m.from_user) + f"\n🕒 Time: <code>{datetime.now(timezone.utc).strftime('%d %b %Y • %H:%M UTC')}</code>")
    await m.answer(
        "✨ <b>Welcome to WishVerse</b>\n\n"
        "Create beautiful interactive Birthday, Valentine, Anniversary, Friendship and Surprise websites directly from Telegram.\n\n"
        "Everything is guided step-by-step with buttons. Tap <b>Create a Wish Website</b> to begin.",
        reply_markup=home_menu()
    )



@dp.callback_query(F.data == "studio_menu")
async def studio_menu_cb(c):
    await c.answer()
    await safe_edit(c.message, "🧠 <b>Creator Studio</b>\n\nChoose how you want to build your experience. Templates are fast; scratch gives you full control.", reply_markup=studio_menu())

@dp.callback_query(F.data == "ideas_menu")
async def ideas_menu_cb(c):
    await c.answer()
    await safe_edit(c.message, "📚 <b>Wish Ideas & Inspiration</b>\n\nTap an occasion for design ideas, recommended opening styles and interactive features.", reply_markup=ideas_menu())

@dp.callback_query(F.data.startswith("idea:"))
async def idea_cb(c):
    await c.answer()
    key=c.data.split(":",1)[1]
    ideas={
      "birthday":"🎂 <b>Birthday</b>\nGift Box opening → Countdown → Photo memories → Confetti → Guestbook.",
      "valentine":"❤️ <b>Valentine</b>\nEnvelope opening → Secret Letter → Love Meter → Rose theme → Memory timeline.",
      "anniversary":"💍 <b>Anniversary</b>\nCinematic opening → Timeline → Photo story → Luxury typography → Guestbook.",
      "surprise":"🎁 <b>Surprise</b>\nMystery opening → Click-to-Reveal → Confetti → Video moment → Secret message.",
      "aesthetic":"🌸 <b>Aesthetic</b>\nTry Garden, Neon, Luxury, Scrapbook, Postcard, Night Universe or Cinematic styles."
    }
    await safe_edit(c.message, ideas.get(key,"💡 Choose an idea."), reply_markup=kb([[InlineKeyboardButton(text="⚡ Use a Template", callback_data="templates_menu")],[InlineKeyboardButton(text="🎨 Create Now", callback_data="categories")],[InlineKeyboardButton(text="🔙 Ideas", callback_data="ideas_menu")]]))

@dp.callback_query(F.data == "home")
async def home(c):
    await safe_edit(c.message, "🏠 <b>WishVerse Main Menu</b>\n\nCreate, manage and track your wish websites from here.", reply_markup=home_menu())
    await c.answer()

@dp.callback_query(F.data == "templates_menu")
async def templates_menu_cb(c):
    await safe_edit(c.message, "⚡ <b>Quick Templates</b>\n\nChoose a professionally prepared starting style. You can still customize the recipient, title, message, media and other details.", reply_markup=template_menu())
    await c.answer()

@dp.callback_query(F.data.startswith("template:"))
async def template_choose(c):
    key=c.data.split(":",1)[1]
    preset=TEMPLATE_PRESETS.get(key)
    if not preset:
        return await c.answer("Template not found.", show_alert=True)
    draft=dict(preset)
    draft["step"]="recipient"
    await save_draft(c.from_user.id, draft)
    await safe_edit(c.message, "⚡ <b>Template loaded!</b>\n\nThe occasion, package, visual style, opening and starter features are ready.\n\nNow send the <b>recipient's name</b>, or send <code>skip</code>.")
    await c.answer("Template ready!")

@dp.callback_query(F.data == "progress_menu")
async def progress_menu_cb(c):
    draft=await get_draft(c.from_user.id)
    rows=[[InlineKeyboardButton(text="➕ Start / Restart Creation", callback_data="categories")],[InlineKeyboardButton(text="⚡ Use Template", callback_data="templates_menu")],[InlineKeyboardButton(text="🏠 Main Menu", callback_data="home")]]
    await safe_edit(c.message, draft_progress_text(draft), reply_markup=kb(rows))
    await c.answer()

@dp.callback_query(F.data == "help_menu")
async def help_menu_cb(c):
    await safe_edit(c.message, 
        "❓ <b>WishVerse Help</b>\n\n"
        "<b>Main commands</b>\n"
        "/start — Open main menu\n"
        "/create — Start a new website\n"
        "/mywebsites — Manage your websites\n"
        "/dashboard — View your dashboard\n"
        "/stats — View statistics\n"
        "/guide — Open the creation guide\n/templates — Quick professional starting templates\n/progress — See current creation progress\n"
        "/cancel — Cancel the current creation\n"
        "/help — Show this help menu\n/ultra — Open Ultra Creator Lab\n/analytics — View live analytics\n"
        "The actual creation uses inline buttons so users do not need to remember commands.",
        reply_markup=kb([[InlineKeyboardButton(text="📖 Open Creation Guide", callback_data="guide_menu")],[InlineKeyboardButton(text="🏠 Main Menu", callback_data="home")]])
    )
    await c.answer()

@dp.callback_query(F.data == "guide_menu")
async def guide_menu_cb(c):
    await safe_edit(c.message, "📖 <b>How to Create Your Website</b>\n\nTap any step below to understand it. You can return and start creating at any time.", reply_markup=guide_menu())
    await c.answer()

@dp.callback_query(F.data.startswith("guide:"))
async def guide_step(c):
    key=c.data.split(":",1)[1]
    info={
      "occasion":"1️⃣ <b>Choose Occasion</b>\nSelect Birthday, Valentine, Anniversary, Friendship, Congratulations, Surprise, Festival or Custom.",
      "package":"2️⃣ <b>Choose Package</b>\n✨ Normal: beautiful website with up to 4 photos.\n💎 Premium: advanced story experience, more media, premium themes and interactive sections.",
      "theme":"3️⃣ <b>Theme & Entrance</b>\nChoose the visual background, then choose how the visitor enters: envelope, gift, portal, cinematic and more.",
      "text":"4️⃣ <b>Text & Fonts</b>\nAdd recipient name, title and wish message. Choose separate fonts for the title and message.",
      "extras":"5️⃣ <b>Interactive Extras</b>\nAdd reveal surprises, letters, countdowns and, for Premium, timelines, love meter, reactions and guestbook.",
      "publish":"6️⃣ <b>Preview & Publish</b>\nPreview privately first. Then choose a Telegram Stars publishing plan. The owner and granted users can publish free permanently."
    }
    await safe_edit(c.message, info.get(key,"Guide step not found."), reply_markup=kb([[InlineKeyboardButton(text="⬅️ Back to Guide", callback_data="guide_menu")],[InlineKeyboardButton(text="➕ Start Creating", callback_data="categories")]]))
    await c.answer()

@dp.callback_query(F.data == "dashboard_menu")
async def dashboard_menu_cb(c):
    sites = await db.websites.find({"owner_id": c.from_user.id}).to_list(length=500)
    now=datetime.now(timezone.utc)
    live=sum(1 for x in sites if x.get("published") and (x.get("is_permanent") or (as_utc(x.get("published_expires_at")) and as_utc(x.get("published_expires_at"))>now)))
    premium=sum(1 for x in sites if x.get("package")=="premium")
    views=sum(int(x.get("views",0) or 0) for x in sites)
    await safe_edit(c.message, f"📊 <b>Your Dashboard</b>\n\n🌐 Total websites: <b>{len(sites)}</b>\n🟢 Live now: <b>{live}</b>\n💎 Premium: <b>{premium}</b>\n👁 Total views: <b>{views}</b>", reply_markup=kb([[InlineKeyboardButton(text="🏠 My Websites", callback_data="mywebsites")],[InlineKeyboardButton(text="➕ Create New", callback_data="categories")],[InlineKeyboardButton(text="🏠 Main Menu", callback_data="home")]]))
    await c.answer()

@dp.callback_query(F.data == "noop")
async def noop(c):
    await c.answer()

@dp.callback_query(F.data == "categories")
async def categories(c):
    await safe_edit(c.message, "🎉 <b>Choose what you want to create</b>", reply_markup=category_menu())
    await c.answer()

@dp.callback_query(F.data.startswith("cat:"))
async def choose_category(c):
    cat = c.data.split(":", 1)[1]
    await save_draft(c.from_user.id, {"type": cat, "step": "package"})
    await safe_edit(c.message, 
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
    draft["step"] = "opening_style"
    await save_draft(c.from_user.id, draft)
    await safe_edit(c.message, 
        f"💎 <b>{info['name']}</b> selected!\n\nNow choose how the visitor enters the story:",
        reply_markup=opening_style_menu("premium")
    )
    await c.answer()

@dp.callback_query(F.data.startswith("theme:"))
async def choose_theme(c):
    theme = c.data.split(":", 1)[1]
    if theme not in THEMES:
        return await c.answer("Theme not found", show_alert=True)
    draft = await get_draft(c.from_user.id) or {}
    draft["theme"] = theme
    draft["step"] = "opening_style"
    await save_draft(c.from_user.id, draft)
    t = THEMES[theme]
    await safe_edit(c.message, 
        f"{t['name']} selected!\n\n"
        f"🎭 <b>Style:</b> {t['mode'].title()}\n"
        f"✨ <b>Effects:</b> {t['effect']}\n\n"
        "Now choose an opening style for this website:",
        reply_markup=opening_style_menu(draft.get("package", "simple"))
    )
    await c.answer()

@dp.callback_query(F.data.startswith("opening:"))
async def choose_opening(c):
    style = c.data.split(":", 1)[1]
    draft = await get_draft(c.from_user.id)
    if not draft or draft.get("step") != "opening_style":
        return await c.answer("Please start again.", show_alert=True)
    draft["opening_style"] = style
    draft["step"] = "recipient"
    await save_draft(c.from_user.id, draft)
    await safe_edit(c.message, "🚪 <b>Opening style selected!</b>\n\nNow send the <b>recipient's name</b>, or send <code>skip</code>.")
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
        await safe_edit(c.message, 
            "✨ <b>Normal Website selected</b>\n\nChoose the background theme. After that you will add the name, title, message, fonts and up to 4 photos.",
            reply_markup=theme_menu(0)
        )
    else:
        draft["step"] = "premium_theme"
        await save_draft(c.from_user.id, draft)
        category = draft.get("type", "custom")
        await safe_edit(c.message, 
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
        await safe_edit(c.message, "💌 Now choose a DIFFERENT font for the wish/message text:", reply_markup=font_menu(draft.get("package"), "message"))
    else:
        draft["message_font"] = font
        draft["step"] = "extras"
        draft.setdefault("photo_file_ids", [])
        await save_draft(c.from_user.id, draft)
        if draft.get("package") == "premium":
            await safe_edit(c.message, "💎 Add premium interactive experiences! You can select multiple:", reply_markup=premium_extras_menu())
        else:
            await safe_edit(c.message, 
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
        await safe_edit(c.message, 
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
        await safe_edit(c.message, 
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
                lines.append(f"{status} • <b>{d.get('title','Untitled')}</b> • 👁 {d.get('views',0)} views\n{BASE_URL}/s/{d['slug']}")
            else:
                lines.append(f"🔒 Draft / Expired • <b>{d.get('title','Untitled')}</b>")
        text = "\n\n".join(lines)
    rows=[]
    for d in docs:
        rows.append([InlineKeyboardButton(text=f"⚙️ Manage • {str(d.get('title','Untitled'))[:28]}", callback_data=f"manage:{d['slug']}")])
    rows += [[InlineKeyboardButton(text="➕ Create New", callback_data="categories")],[InlineKeyboardButton(text="🏠 Main Menu", callback_data="home")]]
    await safe_edit(c.message, text, reply_markup=kb(rows))
    await c.answer()

@dp.callback_query(F.data.startswith("manage:"))
async def manage_site(c):
    slug=c.data.split(":",1)[1]
    site,err=await get_owned_site(slug,c.from_user.id)
    if err: return await c.answer("Website not found.", show_alert=True)
    live=site.get("published")
    text=(f"⚙️ <b>Website Manager</b>\n\n<b>{site.get('title','Untitled')}</b>\n🎨 {site.get('package','simple').title()} • {site.get('type','custom').title()}\n👁 Views: {site.get('views',0)}\n🌐 Status: {'LIVE' if live else 'Draft / Expired'}")
    rows=[[InlineKeyboardButton(text="🚀 Publish / Renew", callback_data=f"publish:{slug}")],[InlineKeyboardButton(text="📈 Analytics", callback_data=f"analytics:{slug}"), InlineKeyboardButton(text="🔗 Share Kit", callback_data=f"share:{slug}")],[InlineKeyboardButton(text="🎛 Ultra Controls", callback_data=f"controls:{slug}"), InlineKeyboardButton(text="📋 Duplicate as New", callback_data=f"duplicate:{slug}")],[InlineKeyboardButton(text="🗑 Delete", callback_data=f"deleteask:{slug}")],[InlineKeyboardButton(text="⬅️ My Websites", callback_data="mywebsites")]]
    await safe_edit(c.message, text, reply_markup=kb(rows)); await c.answer()

@dp.callback_query(F.data.startswith("duplicate:"))
async def duplicate_site(c):
    slug=c.data.split(":",1)[1]
    site,err=await get_owned_site(slug,c.from_user.id)
    if err: return await c.answer("Website not found.", show_alert=True)
    draft={k:site.get(k) for k in ["type","package","theme","opening_style","recipient_name","title","message","title_font","message_font","extras","event_date","surprise_text","letter_text","photo_file_ids","video_file_id"]}
    draft["title"]=(site.get("title") or "Untitled")+" (Copy)"; draft["step"]="extras"
    await save_draft(c.from_user.id,draft)
    await safe_edit(c.message, "📋 <b>Website copied to a new draft.</b>\n\nYou can now continue with features and media without changing the original website.", reply_markup=premium_extras_menu() if draft.get('package')=='premium' else normal_extras_menu())
    await c.answer("Copied!")

@dp.callback_query(F.data.startswith("deleteask:"))
async def delete_ask(c):
    slug=c.data.split(":",1)[1]
    await safe_edit(c.message, "⚠️ <b>Delete this website?</b>\nThis cannot be undone.", reply_markup=kb([[InlineKeyboardButton(text="🗑 Yes, Delete", callback_data=f"deleteyes:{slug}")],[InlineKeyboardButton(text="⬅️ Cancel", callback_data=f"manage:{slug}")]])); await c.answer()

@dp.callback_query(F.data.startswith("deleteyes:"))
async def delete_yes(c):
    slug=c.data.split(":",1)[1]
    result=await db.websites.delete_one({"slug":slug,"owner_id":c.from_user.id})
    if not result.deleted_count: return await c.answer("Website not found.", show_alert=True)
    await safe_edit(c.message, "🗑 Website deleted successfully.", reply_markup=home_menu()); await c.answer("Deleted")

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

@dp.message(F.text & ~F.text.startswith("/"))
async def collect(m):
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
    await safe_edit(c.message, 
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

    await log_event(
        bot,
        "💳 <b>PAYMENT STARTED</b>\n\n"
        f"{user_log_details(c.from_user)}\n"
        f"📦 Package: <b>{site.get('package', 'simple').title()}</b>\n"
        f"⭐ Stars: <b>{plan['stars']} ⭐</b>\n"
        f"⏳ Plan: <b>{plan['label']}</b>\n"
        f"🎨 Website: <code>{slug}</code>\n"
        f"🔗 Preview: {BASE_URL}/preview/{slug}"
    )

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
    if ok:
        await log_event(
            bot,
            "🧾 <b>PAYMENT CHECKOUT CONFIRMED</b>\n\n"
            f"{user_log_details(q.from_user)}\n"
            f"⭐ Amount: <b>{q.total_amount} ⭐</b>\n"
            f"🎨 Website: <code>{p.get('website_slug')}</code>\n"
            f"📦 Package: <b>{p.get('package', 'simple').title()}</b>\n"
            f"⏳ Plan: <b>{p.get('plan')}</b>"
        )
    else:
        await log_event(bot, f"⚠️ <b>INVALID PAYMENT CHECKOUT</b>\n\n{user_log_details(q.from_user)}\n⭐ Amount: <b>{q.total_amount} ⭐</b>")
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
    expiry_text = "Never expires (Permanent)" if expires_at is None else expires_at.strftime("%d %b %Y • %H:%M UTC")
    await log_event(
        m.bot,
        "✅ <b>PAYMENT SUCCESSFUL — WEBSITE PUBLISHED</b>\n\n"
        f"{user_log_details(m.from_user)}\n"
        f"📦 Package: <b>{p.get('package', 'simple').title()}</b>\n"
        f"⭐ Paid: <b>{p['amount']} Stars</b>\n"
        f"⏳ Plan: <b>{p['plan']}</b>\n"
        f"⌛ Expires: <b>{expiry_text}</b>\n"
        f"🎨 Website ID: <code>{p['website_slug']}</code>\n"
        f"🌐 Live: {BASE_URL}/s/{p['website_slug']}\n"
        f"🧾 Telegram Charge: <code>{info.telegram_payment_charge_id}</code>"
    )

@dp.message(Command("create"))
async def create_cmd(m):
    await m.answer("➕ <b>Start a New Wish Website</b>\n\nChoose the occasion:", reply_markup=category_menu())

@dp.message(Command("guide"))
async def guide_cmd(m):
    await m.answer("📖 <b>WishVerse Creation Guide</b>\n\nChoose a step:", reply_markup=guide_menu())

@dp.message(Command("templates"))
async def templates_cmd(m):
    await m.answer("⚡ <b>Quick Templates</b>\n\nChoose a starting style and customize it.", reply_markup=template_menu())

@dp.message(Command("progress"))
async def progress_cmd(m):
    draft=await get_draft(m.from_user.id)
    await m.answer(draft_progress_text(draft), reply_markup=kb([[InlineKeyboardButton(text="➕ Continue / Restart", callback_data="categories")],[InlineKeyboardButton(text="⚡ Templates", callback_data="templates_menu")]]))

@dp.message(Command("cancel"))
async def cancel_cmd(m):
    await db.users.update_one({"telegram_id": m.from_user.id}, {"$unset": {"draft": ""}}, upsert=True)
    await m.answer("❌ Your current creation was cancelled. Your already-created websites were not deleted.", reply_markup=home_menu())

@dp.message(Command("mywebsites"))
async def mywebsites_cmd(m):
    docs = await db.websites.find({"owner_id": m.from_user.id}).sort("created_at", -1).limit(10).to_list(length=10)
    if not docs:
        return await m.answer("🏠 You have not created any websites yet.", reply_markup=home_menu())
    now=datetime.now(timezone.utc)
    lines=["🏠 <b>Your Websites</b>"]
    for d in docs:
        live=bool(d.get("published")) and (d.get("is_permanent") or (as_utc(d.get("published_expires_at")) and as_utc(d.get("published_expires_at"))>now))
        status="🟢 LIVE" if live else "🔒 Draft / Expired"
        lines.append(f"{status} • <b>{d.get('title','Untitled')}</b> • 👁 {d.get('views',0)}")
    await m.answer("\n\n".join(lines), reply_markup=kb([[InlineKeyboardButton(text="🏠 Open Website Manager", callback_data="mywebsites")],[InlineKeyboardButton(text="➕ Create New", callback_data="categories")]]))

@dp.message(Command("stats"))
async def stats(m):
    docs = await db.websites.find({"owner_id": m.from_user.id}).to_list(length=1000)
    total = len(docs)
    live = sum(1 for d in docs if d.get("published"))
    views = sum(int(d.get("views", 0) or 0) for d in docs)
    premium = sum(1 for d in docs if d.get("package") == "premium")
    await m.answer(
        "📊 <b>Your WishVerse Stats</b>\n\n"
        f"🌐 Websites: <b>{total}</b>\n"
        f"🟢 Published: <b>{live}</b>\n"
        f"💎 Premium created: <b>{premium}</b>\n"
        f"👁 Total public views: <b>{views}</b>"
    )

@dp.message(Command("dashboard"))
async def dashboard(message: Message):
    sites = await db.websites.find({"owner_id": message.from_user.id}).to_list(length=500)
    published = sum(1 for x in sites if x.get("published"))
    premium = sum(1 for x in sites if x.get("package") == "premium")
    views = sum(int(x.get("views", 0) or 0) for x in sites)
    await message.answer(
        "📊 <b>Your WishVerse Dashboard</b>\n\n"
        f"🌐 Websites: <b>{len(sites)}</b>\n🟢 Live now: <b>{published}</b>\n💎 Premium: <b>{premium}</b>\n👁 Total views: <b>{views}</b>\n\n"
        "Use 🏠 My Websites to manage your creations.",
        parse_mode="HTML"
    )

@dp.message(Command("help"))
async def help_cmd(m):
    await m.answer("❓ <b>WishVerse Commands & Help</b>\n\nUse the buttons below for a clear guided experience.", reply_markup=kb([[InlineKeyboardButton(text="❓ Open Help", callback_data="help_menu")],[InlineKeyboardButton(text="📖 Creation Guide", callback_data="guide_menu")],[InlineKeyboardButton(text="🏠 Main Menu", callback_data="home")]]))

@dp.message(Command("grantfree"))
async def grantfree(m: Message):
    """Owner: /grantfree USER_ID or reply to a user's message with /grantfree."""
    if not m.from_user or not is_owner(m.from_user.id):
        return await m.answer("⛔ Owner only command.")

    uid = None
    target_user = None
    if m.reply_to_message and m.reply_to_message.from_user:
        target_user = m.reply_to_message.from_user
        uid = target_user.id
    else:
        parts = (m.text or "").split(maxsplit=1)
        if len(parts) == 2 and parts[1].strip().isdigit():
            uid = int(parts[1].strip())

    if not uid:
        return await m.answer(
            "⚠️ <b>How to grant free publishing</b>\n\n"
            "• Reply to a user's message and send <code>/grantfree</code>\n"
            "OR\n"
            "• Send <code>/grantfree USER_ID</code>\n\n"
            "Example: <code>/grantfree 123456789</code>"
        )

    now = datetime.now(timezone.utc)
    update = {
        "$set": {"free_access": True, "free_access_granted_at": now, "free_access_granted_by": m.from_user.id},
        "$setOnInsert": {"telegram_id": uid, "created_at": now},
    }
    if target_user:
        update["$set"].update({
            "username": target_user.username or None,
            "full_name": target_user.full_name or None,
        })
    await db.users.update_one({"telegram_id": uid}, update, upsert=True)

    name = target_user.full_name if target_user else None
    label = f"<b>{name}</b> (<code>{uid}</code>)" if name else f"<code>{uid}</code>"
    await m.answer(
        "✅ <b>Free publishing granted!</b>\n\n"
        f"👤 User: {label}\n"
        "🌐 Normal websites: <b>FREE</b>\n"
        "💎 Premium websites: <b>FREE</b>\n"
        "♾ Access: <b>Permanent until revoked</b>"
    )
    await log_event(m.bot, "👑 <b>FREE ACCESS GRANTED</b>\n" + user_log_details(target_user) + f"\n🛠 Granted by owner: <code>{m.from_user.id}</code>" if target_user else f"👑 <b>FREE ACCESS GRANTED</b>\n👤 User ID: <code>{uid}</code>\n🛠 Granted by owner: <code>{m.from_user.id}</code>")


@dp.message(Command("revokefree"))
async def revokefree(m: Message):
    """Owner: /revokefree USER_ID or reply to a user's message with /revokefree."""
    if not m.from_user or not is_owner(m.from_user.id):
        return await m.answer("⛔ Owner only command.")

    uid = None
    target_user = None
    if m.reply_to_message and m.reply_to_message.from_user:
        target_user = m.reply_to_message.from_user
        uid = target_user.id
    else:
        parts = (m.text or "").split(maxsplit=1)
        if len(parts) == 2 and parts[1].strip().isdigit():
            uid = int(parts[1].strip())

    if not uid:
        return await m.answer(
            "⚠️ <b>How to revoke free publishing</b>\n\n"
            "• Reply to the user's message with <code>/revokefree</code>\n"
            "OR\n"
            "• Send <code>/revokefree USER_ID</code>"
        )

    existing = await db.users.find_one({"telegram_id": uid})
    if not existing or not existing.get("free_access"):
        return await m.answer(f"ℹ️ <code>{uid}</code> does not currently have free publishing access.")

    await db.users.update_one(
        {"telegram_id": uid},
        {"$set": {"free_access": False, "free_access_revoked_at": datetime.now(timezone.utc), "free_access_revoked_by": m.from_user.id}},
    )
    name = target_user.full_name if target_user else existing.get("full_name")
    label = f"<b>{name}</b> (<code>{uid}</code>)" if name else f"<code>{uid}</code>"
    await m.answer(f"❌ <b>Free publishing revoked.</b>\n\n👤 User: {label}\n💳 Future publishing will require Telegram Stars.")
    await log_event(m.bot, f"🚫 <b>FREE ACCESS REVOKED</b>\n👤 User ID: <code>{uid}</code>\n🛠 Revoked by owner: <code>{m.from_user.id}</code>")


@dp.message(Command("freeusers"))
async def freeusers(m: Message):
    if not m.from_user or not is_owner(m.from_user.id):
        return await m.answer("⛔ Owner only command.")

    docs = await db.users.find({"free_access": True}).sort("free_access_granted_at", -1).to_list(length=200)
    if not docs:
        return await m.answer("👑 <b>Free Publishing Users</b>\n\nNo users currently have free publishing access.")

    lines = []
    for i, d in enumerate(docs, 1):
        name = d.get("full_name") or "Unknown user"
        username = f"@{d['username']}" if d.get("username") else "No username"
        lines.append(f"{i}. <b>{name}</b>\n   🔗 {username}\n   🆔 <code>{d.get('telegram_id')}</code>")

    header = f"👑 <b>Free Publishing Users</b>\n\nTotal: <b>{len(docs)}</b>\n\n"
    text = header + "\n\n".join(lines)
    # Telegram message limit protection.
    if len(text) > 4000:
        text = text[:3900] + f"\n\n… Showing first users. Total: {len(docs)}"
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


@dp.message(Command("studio"))
async def studio_command(m: Message):
    await m.answer("🧠 <b>Creator Studio</b>\nBuild faster with templates or start from scratch.", reply_markup=studio_menu())

@dp.message(Command("ideas"))
async def ideas_command(m: Message):
    await m.answer("📚 <b>Ideas & Inspiration</b>", reply_markup=ideas_menu())


# ======================== ULTRA CREATOR LAB ========================
def ultra_menu():
    return kb([
        [InlineKeyboardButton(text="🧠 AI-style Design Assistant", callback_data="ultra:design"), InlineKeyboardButton(text="🎬 Story Director", callback_data="ultra:story")],
        [InlineKeyboardButton(text="🎨 Style Mixer", callback_data="ultra:mixer"), InlineKeyboardButton(text="🧩 Experience Builder", callback_data="ultra:experience")],
        [InlineKeyboardButton(text="📈 Analytics Lab", callback_data="analytics_menu"), InlineKeyboardButton(text="🔗 Viral Share Kit", callback_data="ultra:share")],
        [InlineKeyboardButton(text="🛡 Privacy & Safety", callback_data="ultra:privacy"), InlineKeyboardButton(text="🏆 Creator Achievements", callback_data="ultra:achievements")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="home")]
    ])

@dp.callback_query(F.data == "ultra_lab")
async def ultra_lab_cb(c):
    await c.answer()
    await safe_edit(c.message, 
        "🚀 <b>WishVerse Ultra Creator Lab</b>\n\n"
        "This is your advanced control center. Build websites as interactive experiences—not just pages. "
        "Every tool below is designed to help users make clearer, richer and more shareable websites.",
        reply_markup=ultra_menu())

@dp.callback_query(F.data.startswith("ultra:"))
async def ultra_feature_cb(c):
    await c.answer()
    key=c.data.split(":",1)[1]
    text={
      "design":"🧠 <b>Design Assistant</b>\n\nUse the occasion, mood and recipient to pick a ready direction: Luxury, Cute, Emotional, Party, Dark, Minimal or Cinematic. Start with a Quick Template, then customize every detail.",
      "story":"🎬 <b>Story Director</b>\n\nPremium websites follow a story flow: Hook → Choice → Reveal → Letter → Memories → Video → Finale. This makes the visitor feel like they are experiencing a journey.",
      "mixer":"🎨 <b>Style Mixer</b>\n\nMix background atmosphere, page layout, opening animation, title font and message font independently. Premium themes now support visually different page personalities—not only different colors.",
      "experience":"🧩 <b>Experience Builder</b>\n\nCombine interactive modules such as Surprise Reveal, Secret Letter, Countdown, Memory Timeline, Love Meter, Reaction Wall and Guestbook.",
      "share":"🔗 <b>Viral Share Kit</b>\n\nEach published website can be opened from its Website Manager. The Share Kit gives the live link and makes it easy to copy/share it in Telegram, WhatsApp, Instagram bio or anywhere else.",
      "privacy":"🛡 <b>Privacy & Safety</b>\n\nDrafts stay private. Preview links expire automatically. Public visitors can only access websites after publishing. Owner-managed free access remains protected by your bot owner ID.",
      "achievements":"🏆 <b>Creator Achievements</b>\n\nTrack your progress through your Dashboard: websites created, live websites, premium creations and total views. More advanced creator milestones can be added later without changing the existing website flow."
    }.get(key,"🚀 Ultra feature")
    rows=[]
    if key in {"design","story","mixer","experience"}:
        rows.append([InlineKeyboardButton(text="⚡ Open Templates", callback_data="templates_menu"),InlineKeyboardButton(text="🎨 Build Now", callback_data="categories")])
    rows.append([InlineKeyboardButton(text="⬅️ Ultra Creator Lab", callback_data="ultra_lab")])
    await safe_edit(c.message, text, reply_markup=kb(rows))

@dp.callback_query(F.data == "analytics_menu")
async def analytics_menu_cb(c):
    sites=await db.websites.find({"owner_id":c.from_user.id}).to_list(length=500)
    views=sum(int(x.get("views",0) or 0) for x in sites)
    top=sorted(sites,key=lambda x:int(x.get("views",0) or 0),reverse=True)[:3]
    toptext="\n".join(f"• <b>{(x.get('title') or 'Untitled')[:45]}</b> — {x.get('views',0)} views" for x in top) or "No websites yet."
    await safe_edit(c.message, f"📈 <b>Live Analytics</b>\n\n👁 Total views: <b>{views}</b>\n🌐 Websites tracked: <b>{len(sites)}</b>\n\n🏆 <b>Top websites</b>\n{toptext}", reply_markup=kb([[InlineKeyboardButton(text="🏠 My Websites",callback_data="mywebsites")],[InlineKeyboardButton(text="🚀 Ultra Lab",callback_data="ultra_lab")]]))
    await c.answer()

@dp.callback_query(F.data.startswith("analytics:"))
async def analytics_site_cb(c):
    slug=c.data.split(":",1)[1]
    site,err=await get_owned_site(slug,c.from_user.id)
    if err:return await c.answer("Website not found.",show_alert=True)
    created=site.get("created_at")
    last=site.get("last_viewed_at")
    events=site.get("event_counts", {}) or {}
    reactions=site.get("reaction_counts", {}) or {}
    opens=int(events.get("experience_opened",0) or 0)
    finale=int(events.get("finale_unlocked",0) or 0)
    photos=int(events.get("photo_opened",0) or 0)
    shared=int(events.get("shared",0) or 0)
    reaction_total=sum(int(v or 0) for v in reactions.values())
    analytics_text=(f"📈 <b>Website Analytics</b>\n\n📝 <b>{site.get('title','Untitled')}</b>\n👁 Total views: <b>{site.get('views',0)}</b>\n✨ Experience opens: <b>{opens}</b>\n🏁 Finales unlocked: <b>{finale}</b>\n📸 Photos opened: <b>{photos}</b>\n↗ Shares: <b>{shared}</b>\n💬 Guestbook entries: <b>{site.get('guestbook_count',0)}</b>\n💖 Reactions: <b>{reaction_total}</b>\n🕒 Last view: <code>{last or 'No visitor yet'}</code>\n📅 Created: <code>{created or 'Unknown'}</code>\n\nInteraction analytics are collected automatically on published Premium experiences.")
    await safe_edit(c.message, analytics_text, reply_markup=kb([[InlineKeyboardButton(text="⬅️ Website Manager",callback_data=f"manage:{slug}")]]))
    await c.answer()

@dp.callback_query(F.data.startswith("share:"))
async def share_site_cb(c):
    slug=c.data.split(":",1)[1]
    site,err=await get_owned_site(slug,c.from_user.id)
    if err:return await c.answer("Website not found.",show_alert=True)
    if not site.get("published"):
        return await c.answer("Publish the website first to get a public share link.",show_alert=True)
    await safe_edit(c.message, f"🔗 <b>Share Kit</b>\n\n🌐 Your live website:\n<code>{BASE_URL}/s/{slug}</code>\n\nCopy this link and share it anywhere. Your view analytics will update when visitors open the public website.", reply_markup=kb([[InlineKeyboardButton(text="⬅️ Website Manager",callback_data=f"manage:{slug}")]]))
    await c.answer()

@dp.callback_query(F.data.startswith("controls:"))
async def controls_cb(c):
    slug=c.data.split(":",1)[1]
    site,err=await get_owned_site(slug,c.from_user.id)
    if err:return await c.answer("Website not found.",show_alert=True)
    await safe_edit(c.message, "🎛 <b>Ultra Website Controls</b>\n\nManage and improve this creation from one place.",reply_markup=kb([
      [InlineKeyboardButton(text="📈 Analytics",callback_data=f"analytics:{slug}"),InlineKeyboardButton(text="🔗 Share Kit",callback_data=f"share:{slug}")],
      [InlineKeyboardButton(text="📋 Duplicate & Remix",callback_data=f"duplicate:{slug}")],
      [InlineKeyboardButton(text="🚀 Publish / Renew",callback_data=f"publish:{slug}")],
      [InlineKeyboardButton(text="⬅️ Website Manager",callback_data=f"manage:{slug}")]
    ]))
    await c.answer()

@dp.message(Command("ultra"))
async def ultra_cmd(m):
    await m.answer("🚀 <b>WishVerse Ultra Creator Lab</b>",reply_markup=ultra_menu())

@dp.message(Command("analytics"))
async def analytics_cmd(m):
    sites=await db.websites.find({"owner_id":m.from_user.id}).to_list(length=500)
    views=sum(int(x.get("views",0) or 0) for x in sites)
    await m.answer(f"📈 <b>Your Analytics</b>\n\n👁 Total views: <b>{views}</b>\n🌐 Websites: <b>{len(sites)}</b>",reply_markup=kb([[InlineKeyboardButton(text="📈 Open Full Analytics",callback_data="analytics_menu")]]))

# ======================== ULTRA CREATOR V8 ========================
def v8_builder_menu():
    return kb([
        [InlineKeyboardButton(text="🎨 Design", callback_data="v8:design"), InlineKeyboardButton(text="📝 Content", callback_data="v8:content")],
        [InlineKeyboardButton(text="🖼 Media", callback_data="v8:media"), InlineKeyboardButton(text="✨ Effects", callback_data="v8:effects")],
        [InlineKeyboardButton(text="🧩 Sections", callback_data="v8:sections"), InlineKeyboardButton(text="🎬 Story Mode", callback_data="v8:story")],
        [InlineKeyboardButton(text="🎮 Interactions", callback_data="v8:interactions"), InlineKeyboardButton(text="🔐 Privacy", callback_data="v8:privacy")],
        [InlineKeyboardButton(text="⏰ Schedule", callback_data="v8:schedule"), InlineKeyboardButton(text="🧠 Smart Assistant", callback_data="v8:assistant")],
        [InlineKeyboardButton(text="👁 Preview", callback_data="v8:preview"), InlineKeyboardButton(text="🚀 Start Creating", callback_data="categories")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="home")]
    ])

@dp.callback_query(F.data == "v8_builder")
async def v8_builder(c):
    await c.answer()
    await safe_edit(c.message, 
        "🧱 <b>WishVerse Experience Builder</b>\n\n"
        "Build a complete interactive experience from one control panel. Choose what you want to customize; the guided creator keeps the process simple.",
        reply_markup=v8_builder_menu())

@dp.callback_query(F.data.startswith("v8:"))
async def v8_feature(c):
    await c.answer()
    key=c.data.split(":",1)[1]
    data={
      "design":"🎨 <b>Design Studio</b>\n\nChoose atmosphere, page personality, layout, title font, message font, colors and opening style. Premium themes can combine these independently.",
      "content":"📝 <b>Content Studio</b>\n\nControl recipient, title, long wish, signature, secret message and final message. Title and message fonts stay independently customizable.",
      "media":"🖼 <b>Media Studio</b>\n\nAdd photo memories and video moments. Normal websites support the existing photo allowance; Premium supports the advanced media experience.",
      "effects":"✨ <b>Animation Studio</b>\n\nPremium effects can include flowers, petals, butterflies, clouds, fireworks, balloons, hearts, stars, ocean movement and cinematic reveals.",
      "sections":"🧩 <b>Section Builder</b>\n\nBuild with Welcome, Main Wish, Gallery, Video, Timeline, Surprise, Secret Letter, Countdown, Guestbook and Finale sections.",
      "story":"🎬 <b>Story Mode</b>\n\nCreate a visitor journey: Hook → Continue → Memory → Choice → Reveal → Letter → Finale. This makes a wish feel like an interactive story.",
      "interactions":"🎮 <b>Interactive Experience</b>\n\nPremium ideas: Love Meter, Reaction Wall, Guestbook, hidden surprise, reveal buttons, memory choices and celebration effects.",
      "privacy":"🔐 <b>Privacy Controls</b>\n\nDrafts remain private. Preview links expire. Published sites can later support public, link-only, password and scheduled access modes.",
      "schedule":"⏰ <b>Scheduled Reveal</b>\n\nPrepare the website early and schedule the surprise for a special moment such as midnight on a birthday or Valentine’s Day.",
      "assistant":"🧠 <b>Smart Design Assistant</b>\n\nPick a feeling—Romantic, Emotional, Funny, Magical, Luxury, Party or Cute—and use templates as a professional starting point.",
      "preview":"👁 <b>Preview</b>\n\nThe current secure preview remains private and temporary. Public sharing only becomes available after publishing or free-owner/free-user publishing."
    }
    rows=[]
    if key in {"design","content","media","effects","sections","story","interactions","assistant"}:
        rows.append([InlineKeyboardButton(text="⚡ Use Template", callback_data="templates_menu"), InlineKeyboardButton(text="➕ Create Now", callback_data="categories")])
    rows.append([InlineKeyboardButton(text="⬅️ Experience Builder", callback_data="v8_builder")])
    await safe_edit(c.message, data.get(key,"🧱 Experience Builder"), reply_markup=kb(rows))

@dp.message(Command("builder"))
async def builder_cmd(m):
    await m.answer("🧱 <b>WishVerse Experience Builder</b>", reply_markup=v8_builder_menu())

@dp.message(Command("logstatus"))
async def logstatus_cmd(m):
    if not is_owner(m.from_user.id):
        return await m.answer("⛔ Owner only command.")
    if LOG_GROUP_ID:
        await m.answer(f"📡 <b>Logger status: ACTIVE</b>\n\nLog group: <code>{LOG_GROUP_ID}</code>\n\nThe bot logs starts, payment starts, checkout confirmation, successful payments and free-access changes.")
    else:
        await m.answer("⚠️ <b>Logger is not configured.</b>\n\nSet <code>LOG_GROUP_ID</code> in Heroku Config Vars and redeploy.")
