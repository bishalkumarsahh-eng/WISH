import asyncio
import logging
import secrets
import re
from datetime import datetime, timezone
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery
)
from .config import BOT_TOKEN, OWNER_ID, BASE_URL
from .db import db

dp = Dispatcher()

def is_owner(user_id: int) -> bool:
    return bool(OWNER_ID and user_id == OWNER_ID)

def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)

def main_menu():
    return kb([
        [InlineKeyboardButton(text="🎂 Birthday", callback_data="type:birthday"),
         InlineKeyboardButton(text="❤️ Valentine", callback_data="type:valentine")],
        [InlineKeyboardButton(text="💍 Anniversary", callback_data="type:anniversary"),
         InlineKeyboardButton(text="👫 Friendship", callback_data="type:friendship")],
        [InlineKeyboardButton(text="🎉 Congratulations", callback_data="type:congratulations"),
         InlineKeyboardButton(text="🎁 Surprise", callback_data="type:surprise")],
        [InlineKeyboardButton(text="✨ Custom Website", callback_data="type:custom")],
        [InlineKeyboardButton(text="🌐 My Websites", callback_data="my:websites")]
    ])

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "✨ <b>Welcome to WishVerse</b>\n\nCreate a beautiful personalized website for someone special. 💖\n\nChoose what you want to create:",
        reply_markup=main_menu()
    )

@dp.callback_query(F.data.startswith("type:"))
async def choose_type(call: CallbackQuery):
    website_type = call.data.split(":", 1)[1]
    await call.message.edit_text(
        f"🎨 <b>{website_type.title()} Website</b>\n\nChoose a background:",
        reply_markup=kb([
            [InlineKeyboardButton(text="🌈 Gradient", callback_data=f"bg:{website_type}:gradient"),
             InlineKeyboardButton(text="✨ Floating Effects", callback_data=f"bg:{website_type}:hearts")],
            [InlineKeyboardButton(text="🌸 Falling Flowers", callback_data=f"bg:{website_type}:flowers"),
             InlineKeyboardButton(text="🎈 Balloons", callback_data=f"bg:{website_type}:balloons")],
            [InlineKeyboardButton(text="🌟 Moving Stars", callback_data=f"bg:{website_type}:stars")]
        ])
    )
    await call.answer()

@dp.callback_query(F.data.startswith("bg:"))
async def choose_background(call: CallbackQuery):
    _, website_type, background = call.data.split(":", 2)
    await db.users.update_one(
        {"telegram_id": call.from_user.id},
        {"$set": {"draft": {"type": website_type, "background": background, "step": "title"}}},
        upsert=True
    )
    await call.message.edit_text(
        "📝 Send the <b>title</b> for the website.\n\nExample: <i>Happy Birthday Priya! 🎂💖</i>"
    )
    await call.answer()

@dp.message(Command("mywebsites"))
async def my_websites(message: Message):
    sites = await db.websites.find({"owner_id": message.from_user.id}).sort("created_at", -1).to_list(30)
    if not sites:
        await message.answer("🌐 You have not created any websites yet. Use /start to create one.")
        return
    rows = []
    for site in sites:
        rows.append([InlineKeyboardButton(
            text=f"{'🟢' if site.get('published') else '🟡'} {site.get('title','Untitled')[:28]}",
            url=f"{BASE_URL}/s/{site['slug']}" if BASE_URL else None,
            callback_data=f"site:{site['slug']}" if not BASE_URL else None
        )])
    await message.answer("🌐 <b>My Websites</b>", reply_markup=kb(rows))

@dp.message(Command("admin"))
async def admin(message: Message):
    if not is_owner(message.from_user.id):
        return
    users = await db.users.count_documents({})
    sites = await db.websites.count_documents({})
    paid = await db.payments.count_documents({"status": "paid"})
    await message.answer(
        f"👑 <b>OWNER PANEL</b>\n\n👥 Users: {users}\n🌐 Websites: {sites}\n⭐ Paid Orders: {paid}\n\n"
        "Use /grantfree USER_ID or /revokefree USER_ID"
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
    await db.users.update_one({"telegram_id": uid}, {"$set": {"free_access": True}}, upsert=True)
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
    await db.users.update_one({"telegram_id": uid}, {"$set": {"free_access": False}}, upsert=True)
    await message.answer(f"❌ Free access removed from <code>{uid}</code>.")

@dp.message(F.text)
async def collect_draft(message: Message):
    if message.text.startswith("/"):
        return
    user = await db.users.find_one({"telegram_id": message.from_user.id})
    draft = (user or {}).get("draft")
    if not draft:
        return
    if draft.get("step") == "title":
        draft["title"] = message.text[:120]
        draft["step"] = "message"
        await db.users.update_one({"telegram_id": message.from_user.id}, {"$set": {"draft": draft}})
        await message.answer("💌 Now send the beautiful message/wish for the website.")
        return
    if draft.get("step") == "message":
        draft["message"] = message.text[:5000]
        draft["step"] = "confirm"
        slug = secrets.token_urlsafe(7).replace("_", "").replace("-", "")
        site = {
            "slug": slug,
            "owner_id": message.from_user.id,
            "owner_name": message.from_user.full_name,
            "type": draft["type"],
            "background": draft["background"],
            "title": draft["title"],
            "message": draft["message"],
            "published": False,
            "created_at": datetime.now(timezone.utc),
        }
        await db.websites.insert_one(site)
        await db.users.update_one({"telegram_id": message.from_user.id}, {"$unset": {"draft": ""}})
        preview = f"{BASE_URL}/s/{slug}" if BASE_URL else "Set BASE_URL first"
        await message.answer(
            f"👀 <b>Your website preview is ready!</b>\n\n🌐 {preview}\n\nPublish it now?",
            reply_markup=kb([
                [InlineKeyboardButton(text="🚀 Publish / Pay ⭐", callback_data=f"publish:{slug}")],
                [InlineKeyboardButton(text="📝 Create Another", callback_data="restart")]
            ])
        )

@dp.callback_query(F.data == "restart")
async def restart(call: CallbackQuery):
    await call.message.edit_text("Choose what you want to create:", reply_markup=main_menu())
    await call.answer()

@dp.callback_query(F.data.startswith("publish:"))
async def publish(call: CallbackQuery, bot: Bot):
    slug = call.data.split(":", 1)[1]
    site = await db.websites.find_one({"slug": slug, "owner_id": call.from_user.id})
    if not site:
        await call.answer("Website not found.", show_alert=True)
        return
    user = await db.users.find_one({"telegram_id": call.from_user.id}) or {}
    if user.get("free_access"):
        await db.websites.update_one({"slug": slug}, {"$set": {"published": True}})
        await call.message.answer(f"🎉 <b>Published for FREE!</b>\n🌐 {BASE_URL}/s/{slug}")
        await call.answer()
        return

    payload = f"wishverse:{slug}:{call.from_user.id}:{secrets.token_urlsafe(12)}"
    await db.payments.insert_one({
        "payload": payload, "website_slug": slug, "user_id": call.from_user.id,
        "amount": 100, "status": "pending", "created_at": datetime.now(timezone.utc)
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
    await call.answer()

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, bot: Bot):
    payment = await db.payments.find_one({"payload": query.invoice_payload, "status": "pending"})
    if not payment or payment["user_id"] != query.from_user.id or payment["amount"] != query.total_amount:
        await bot.answer_pre_checkout_query(query.id, ok=False, error_message="Invalid or expired payment.")
        return
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    payment_info = message.successful_payment
    existing = await db.payments.find_one({"telegram_payment_charge_id": payment_info.telegram_payment_charge_id})
    if existing:
        return
    payment = await db.payments.find_one({"payload": payment_info.invoice_payload, "status": "pending"})
    if not payment:
        return
    if payment["user_id"] != message.from_user.id or payment["amount"] != payment_info.total_amount:
        return
    await db.payments.update_one(
        {"_id": payment["_id"], "status": "pending"},
        {"$set": {
            "status": "paid",
            "telegram_payment_charge_id": payment_info.telegram_payment_charge_id,
            "provider_payment_charge_id": payment_info.provider_payment_charge_id,
            "paid_at": datetime.now(timezone.utc)
        }}
    )
    await db.websites.update_one({"slug": payment["website_slug"]}, {"$set": {"published": True}})
    await message.answer(
        f"🎉 <b>Payment successful! Your website is LIVE.</b>\n🌐 {BASE_URL}/s/{payment['website_slug']}"
    )

async def run_bot():
    if not BOT_TOKEN:
        logging.warning("BOT_TOKEN is missing. Bot is disabled.")
        return
    bot = Bot(BOT_TOKEN, parse_mode="HTML")
    await dp.start_polling(bot)

def start_bot_background():
    asyncio.create_task(run_bot())
