import asyncio
import logging
import secrets
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
)

from .config import BOT_TOKEN, OWNER_ID, BASE_URL
from .db import db, setup_indexes

log = logging.getLogger(__name__)
dp = Dispatcher()

def is_owner(uid: int) -> bool:
    return bool(OWNER_ID and uid == OWNER_ID)

def keyboard(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)

def menu():
    return keyboard([
        [
            InlineKeyboardButton(text="🎂 Birthday", callback_data="type:birthday"),
            InlineKeyboardButton(text="❤️ Valentine", callback_data="type:valentine")
        ],
        [
            InlineKeyboardButton(text="💍 Anniversary", callback_data="type:anniversary"),
            InlineKeyboardButton(text="👫 Friendship", callback_data="type:friendship")
        ],
        [
            InlineKeyboardButton(text="🎉 Congratulations", callback_data="type:congratulations"),
            InlineKeyboardButton(text="🎁 Surprise", callback_data="type:surprise")
        ],
        [InlineKeyboardButton(text="✨ Custom Website", callback_data="type:custom")]
    ])

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "✨ <b>Welcome to WishVerse</b>\n\n"
        "Create a beautiful personalized surprise website. 💖\n\n"
        "Choose what you want to create:",
        reply_markup=menu()
    )

@dp.callback_query(F.data.startswith("type:"))
async def choose_type(call: CallbackQuery):
    website_type = call.data.split(":", 1)[1]
    await call.message.edit_text(
        "🎨 <b>Choose a background</b>",
        reply_markup=keyboard([
            [
                InlineKeyboardButton(text="🌈 Gradient", callback_data=f"bg:{website_type}:gradient"),
                InlineKeyboardButton(text="💖 Floating Hearts", callback_data=f"bg:{website_type}:hearts")
            ],
            [
                InlineKeyboardButton(text="🌸 Falling Flowers", callback_data=f"bg:{website_type}:flowers"),
                InlineKeyboardButton(text="🎈 Balloons", callback_data=f"bg:{website_type}:balloons")
            ],
            [InlineKeyboardButton(text="🌟 Moving Stars", callback_data=f"bg:{website_type}:stars")]
        ])
    )
    await call.answer()

@dp.callback_query(F.data.startswith("bg:"))
async def choose_background(call: CallbackQuery):
    _, website_type, background = call.data.split(":", 2)
    await db.users.update_one(
        {"telegram_id": call.from_user.id},
        {"$set": {
            "draft": {
                "type": website_type,
                "background": background,
                "step": "title"
            }
        }},
        upsert=True
    )
    await call.message.edit_text("📝 Send the <b>website title</b>.")
    await call.answer()

@dp.message(F.text)
async def collect_text(message: Message):
    if message.text.startswith("/"):
        return

    user = await db.users.find_one({"telegram_id": message.from_user.id})
    draft = (user or {}).get("draft")
    if not draft:
        return

    if draft.get("step") == "title":
        draft["title"] = message.text[:120]
        draft["step"] = "message"
        await db.users.update_one(
            {"telegram_id": message.from_user.id},
            {"$set": {"draft": draft}}
        )
        await message.answer("💌 Now send the beautiful message/wish.")
        return

    if draft.get("step") == "message":
        slug = secrets.token_urlsafe(8).replace("-", "").replace("_", "")
        preview_token = secrets.token_urlsafe(24)

        site = {
            "slug": slug,
            "preview_token": preview_token,
            "owner_id": message.from_user.id,
            "type": draft["type"],
            "background": draft["background"],
            "title": draft["title"],
            "message": message.text[:5000],
            "published": False,
            "created_at": datetime.now(timezone.utc)
        }

        await db.websites.insert_one(site)
        await db.users.update_one(
            {"telegram_id": message.from_user.id},
            {"$unset": {"draft": ""}}
        )

        preview_url = f"{BASE_URL}/preview/{slug}?token={preview_token}"

        await message.answer(
            f"👀 <b>Your private preview is ready!</b>\n\n"
            f"🔒 Preview: {preview_url}\n"
            f"🌐 Public link after publishing: {BASE_URL}/s/{slug}",
            reply_markup=keyboard([
                [InlineKeyboardButton(text="👀 Open Preview", url=preview_url)],
                [InlineKeyboardButton(text="🚀 Publish / Pay ⭐", callback_data=f"publish:{slug}")]
            ])
        )

@dp.callback_query(F.data.startswith("publish:"))
async def publish(call: CallbackQuery, bot: Bot):
    slug = call.data.split(":", 1)[1]
    site = await db.websites.find_one(
        {"slug": slug, "owner_id": call.from_user.id}
    )

    if not site:
        await call.answer("Website not found.", show_alert=True)
        return

    if site.get("published"):
        await call.answer("Already published!", show_alert=True)
        return

    user = await db.users.find_one({"telegram_id": call.from_user.id}) or {}

    if user.get("free_access"):
        await db.websites.update_one(
            {"slug": slug},
            {"$set": {"published": True, "published_at": datetime.now(timezone.utc)}}
        )
        await call.message.answer(
            f"🎉 <b>Published for FREE!</b>\n\n"
            f"🌐 {BASE_URL}/s/{slug}"
        )
        await call.answer()
        return

    payload = f"wishverse:{slug}:{call.from_user.id}:{secrets.token_urlsafe(12)}"

    await db.payments.insert_one({
        "payload": payload,
        "website_slug": slug,
        "user_id": call.from_user.id,
        "amount": 100,
        "status": "pending",
        "created_at": datetime.now(timezone.utc)
    })

    await bot.send_invoice(
        chat_id=call.from_user.id,
        title="Publish Your Wish Website",
        description=f"Publish: {site['title']}",
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Website Publishing", amount=100)]
    )

    await call.answer("Opening secure Telegram Stars payment...")

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, bot: Bot):
    payment = await db.payments.find_one({
        "payload": query.invoice_payload,
        "status": "pending"
    })

    valid = bool(
        payment
        and payment["user_id"] == query.from_user.id
        and payment["amount"] == query.total_amount
    )

    if not valid:
        await bot.answer_pre_checkout_query(
            query.id,
            ok=False,
            error_message="Invalid or expired payment."
        )
        return

    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    payment_info = message.successful_payment

    duplicate = await db.payments.find_one({
        "telegram_payment_charge_id": payment_info.telegram_payment_charge_id
    })

    if duplicate:
        return

    payment = await db.payments.find_one({
        "payload": payment_info.invoice_payload,
        "status": "pending"
    })

    if not payment:
        log.warning("Successful payment received but pending payment was not found.")
        return

    if (
        payment["user_id"] != message.from_user.id
        or payment["amount"] != payment_info.total_amount
    ):
        log.warning("Payment validation failed for user %s", message.from_user.id)
        return

    result = await db.payments.update_one(
        {"_id": payment["_id"], "status": "pending"},
        {"$set": {
            "status": "paid",
            "telegram_payment_charge_id": payment_info.telegram_payment_charge_id,
            "provider_payment_charge_id": payment_info.provider_payment_charge_id,
            "paid_at": datetime.now(timezone.utc)
        }}
    )

    if result.modified_count != 1:
        return

    await db.websites.update_one(
        {"slug": payment["website_slug"]},
        {"$set": {
            "published": True,
            "published_at": datetime.now(timezone.utc)
        }}
    )

    await message.answer(
        f"🎉 <b>Payment successful! Your website is LIVE.</b>\n\n"
        f"🌐 {BASE_URL}/s/{payment['website_slug']}"
    )

@dp.message(Command("grantfree"))
async def grant_free(message: Message):
    if not is_owner(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Usage: /grantfree USER_ID")
        return

    uid = int(parts[1])
    await db.users.update_one(
        {"telegram_id": uid},
        {"$set": {"free_access": True}},
        upsert=True
    )
    await message.answer(f"✅ Free access granted to <code>{uid}</code>.")

@dp.message(Command("revokefree"))
async def revoke_free(message: Message):
    if not is_owner(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Usage: /revokefree USER_ID")
        return

    uid = int(parts[1])
    await db.users.update_one(
        {"telegram_id": uid},
        {"$set": {"free_access": False}},
        upsert=True
    )
    await message.answer(f"❌ Free access removed from <code>{uid}</code>.")

async def run_bot():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")
    if db is None:
        raise RuntimeError("MONGO_URI is missing")
    if not BASE_URL:
        raise RuntimeError("BASE_URL is missing")

    log.info("🤖 Starting WishVerse bot...")
    await setup_indexes()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )

    try:
        await bot.delete_webhook(drop_pending_updates=False)
        me = await bot.get_me()
        log.info("🤖 Bot authenticated successfully: @%s", me.username)
        log.info("🤖 Polling started. Worker should remain online.")
        await dp.start_polling(
            bot,
            handle_signals=True,
            close_bot_session=True
        )
    except asyncio.CancelledError:
        log.info("🤖 Bot task cancelled.")
        raise
    except Exception:
        log.exception("❌ Bot worker crashed.")
        raise
    finally:
        await bot.session.close()
        log.info("🤖 Bot session closed.")
