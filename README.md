# WishVerse — Fixed Heroku Version

## Heroku Config Vars
BOT_TOKEN
OWNER_ID
MONGO_URI
BASE_URL
SECRET_KEY

## Dynos
Scale exactly:
- web = 1
- worker = 1

The web dyno serves websites only.
The worker dyno runs Telegram polling only.

Do not run the same BOT_TOKEN on another Heroku app, Railway, Replit, Render, or local computer.
