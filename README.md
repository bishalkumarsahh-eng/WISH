# WishVerse — Telegram Website Maker

Create birthday, valentine, anniversary and custom wish websites from Telegram.

## Features
- Telegram bot creation flow with inline buttons
- Birthday, Valentine, Anniversary, Friendship, Congratulations, Surprise and Custom types
- Static image, gradient and live animated backgrounds
- Custom title/message and photo uploads
- Dynamic website pages with unique slugs
- Preview and publish flow
- Telegram Stars invoices (XTR)
- Owner free-access whitelist
- MongoDB
- Heroku-ready FastAPI deployment

## Heroku Config Vars
BOT_TOKEN
OWNER_ID
MONGO_URI
BASE_URL
SECRET_KEY

## Commands
/start — open creator
/mywebsites — manage your websites
/admin — owner panel
/grantfree USER_ID — grant unlimited free publishing
/revokefree USER_ID — remove free access

## Important
Telegram Stars payment code validates pre-checkout and only publishes after a successful_payment update.
For production, configure MongoDB Atlas network access and use a persistent media storage service for large files.
