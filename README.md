# WishVerse — Preview + Publish Fixed

## Heroku Config Vars
BOT_TOKEN
OWNER_ID
MONGO_URI
BASE_URL
SECRET_KEY

## Heroku Dynos
Run exactly:
- web = 1
- worker = 1

The Procfile explicitly uses one Uvicorn worker.

## Website flow
1. User creates a draft.
2. A private preview URL is generated.
3. Public `/s/<slug>` remains unavailable until payment/free access.
4. Successful Telegram Stars payment publishes the site.

Do not run this BOT_TOKEN on another server while polling is enabled.
