import logging, secrets
from datetime import datetime, timezone
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
from .config import BOT_TOKEN, OWNER_ID, BASE_URL
from .db import db, setup_indexes

dp = Dispatcher()

def is_owner(uid):
    return bool(OWNER_ID and uid == OWNER_ID)

def keyboard(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)

def menu():
    return keyboard([
        [InlineKeyboardButton(text="🎂 Birthday", callback_data="type:birthday"), InlineKeyboardButton(text="❤️ Valentine", callback_data="type:valentine")],
        [InlineKeyboardButton(text="💍 Anniversary", callback_data="type:anniversary"), InlineKeyboardButton(text="👫 Friendship", callback_data="type:friendship")],
        [InlineKeyboardButton(text="🎉 Congratulations", callback_data="type:congratulations"), InlineKeyboardButton(text="🎁 Surprise", callback_data="type:surprise")],
        [InlineKeyboardButton(text="✨ Custom Website", callback_data="type:custom")],
        [InlineKeyboardButton(text="🌐 My Websites", callback_data="my:websites")]
    ])

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("✨ <b>Welcome to WishVerse</b>\n\nCreate a beautiful personalized website. 💖\n\nChoose what you want to create:", reply_markup=menu())

@dp.callback_query(F.data.startswith("type:"))
async def choose_type(call: CallbackQuery):
    t = call.data.split(":",1)[1]
    await call.message.edit_text("🎨 <b>Choose a background</b>", reply_markup=keyboard([
        [InlineKeyboardButton(text="🌈 Gradient", callback_data=f"bg:{t}:gradient"), InlineKeyboardButton(text="💖 Floating Hearts", callback_data=f"bg:{t}:hearts")],
        [InlineKeyboardButton(text="🌸 Falling Flowers", callback_data=f"bg:{t}:flowers"), InlineKeyboardButton(text="🎈 Balloons", callback_data=f"bg:{t}:balloons")],
        [InlineKeyboardButton(text="🌟 Moving Stars", callback_data=f"bg:{t}:stars")]
    ]))
    await call.answer()

@dp.callback_query(F.data.startswith("bg:"))
async def choose_bg(call: CallbackQuery):
    _, t, bg = call.data.split(":",2)
    await db.users.update_one({"telegram_id":call.from_user.id},{"$set":{"draft":{"type":t,"background":bg,"step":"title"}}},upsert=True)
    await call.message.edit_text("📝 Send the <b>website title</b>.")
    await call.answer()

@dp.message(F.text)
async def collect(message: Message):
    if message.text.startswith("/"):
        return
    user = await db.users.find_one({"telegram_id":message.from_user.id})
    draft = (user or {}).get("draft")
    if not draft:
        return
    if draft["step"] == "title":
        draft["title"] = message.text[:120]; draft["step"] = "message"
        await db.users.update_one({"telegram_id":message.from_user.id},{"$set":{"draft":draft}})
        await message.answer("💌 Now send the message/wish.")
        return
    if draft["step"] == "message":
        slug = secrets.token_urlsafe(7).replace("-","").replace("_","")
        await db.websites.insert_one({"slug":slug,"owner_id":message.from_user.id,"type":draft["type"],"background":draft["background"],"title":draft["title"],"message":message.text[:5000],"published":False,"created_at":datetime.now(timezone.utc)})
        await db.users.update_one({"telegram_id":message.from_user.id},{"$unset":{"draft":""}})
        await message.answer(f"👀 Preview ready!\n🌐 {BASE_URL}/s/{slug}\n\nPublish it?",reply_markup=keyboard([[InlineKeyboardButton(text="🚀 Publish / Pay ⭐",callback_data=f"publish:{slug}")]]))

@dp.callback_query(F.data.startswith("publish:"))
async def publish(call: CallbackQuery, bot: Bot):
    slug=call.data.split(":",1)[1]
    site=await db.websites.find_one({"slug":slug,"owner_id":call.from_user.id})
    if not site: return
    user=await db.users.find_one({"telegram_id":call.from_user.id}) or {}
    if user.get("free_access"):
        await db.websites.update_one({"slug":slug},{"$set":{"published":True}})
        await call.message.answer(f"🎉 Published for FREE!\n🌐 {BASE_URL}/s/{slug}")
        return
    payload=f"wishverse:{slug}:{call.from_user.id}:{secrets.token_urlsafe(10)}"
    await db.payments.insert_one({"payload":payload,"website_slug":slug,"user_id":call.from_user.id,"amount":100,"status":"pending"})
    await bot.send_invoice(chat_id=call.from_user.id,title="Publish Your Wish Website",description=site["title"],payload=payload,provider_token="",currency="XTR",prices=[LabeledPrice(label="Website Publishing",amount=100)])
    await call.answer()

@dp.pre_checkout_query()
async def checkout(q: PreCheckoutQuery, bot: Bot):
    p=await db.payments.find_one({"payload":q.invoice_payload,"status":"pending"})
    ok=bool(p and p["user_id"]==q.from_user.id and p["amount"]==q.total_amount)
    await bot.answer_pre_checkout_query(q.id,ok=ok,error_message=None if ok else "Invalid payment.")

@dp.message(F.successful_payment)
async def paid(message: Message):
    s=message.successful_payment
    p=await db.payments.find_one({"payload":s.invoice_payload,"status":"pending"})
    if not p or p["user_id"]!=message.from_user.id or p["amount"]!=s.total_amount: return
    exists=await db.payments.find_one({"telegram_payment_charge_id":s.telegram_payment_charge_id})
    if exists: return
    await db.payments.update_one({"_id":p["_id"]},{"$set":{"status":"paid","telegram_payment_charge_id":s.telegram_payment_charge_id,"paid_at":datetime.now(timezone.utc)}})
    await db.websites.update_one({"slug":p["website_slug"]},{"$set":{"published":True}})
    await message.answer(f"🎉 <b>Payment successful! Website is LIVE.</b>\n🌐 {BASE_URL}/s/{p['website_slug']}")

@dp.message(Command("grantfree"))
async def grant(message: Message):
    if not is_owner(message.from_user.id): return
    parts=message.text.split()
    if len(parts)!=2 or not parts[1].isdigit():
        await message.answer("Usage: /grantfree USER_ID"); return
    await db.users.update_one({"telegram_id":int(parts[1])},{"$set":{"free_access":True}},upsert=True)
    await message.answer("✅ Free access granted.")

@dp.message(Command("revokefree"))
async def revoke(message: Message):
    if not is_owner(message.from_user.id): return
    parts=message.text.split()
    if len(parts)!=2 or not parts[1].isdigit():
        await message.answer("Usage: /revokefree USER_ID"); return
    await db.users.update_one({"telegram_id":int(parts[1])},{"$set":{"free_access":False}},upsert=True)
    await message.answer("❌ Free access removed.")

async def run_bot():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")
    await setup_indexes()
    bot=Bot(token=BOT_TOKEN,default=DefaultBotProperties(parse_mode="HTML"))
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot, handle_signals=True, close_bot_session=True)
    finally:
        await bot.session.close()
