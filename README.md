# WishVerse Professional Media + Fonts

## New packages

### ✨ Simple Package
- 1 optional photo
- Professional layout
- 4 professional font choices
- Publishing prices:
  - 25 Telegram Stars → 2 hours
  - 50 Telegram Stars → 15 hours
  - 100 Telegram Stars → permanent

### 💎 Premium Package
- Up to 8 photos
- 1 optional video
- All simple fonts plus luxury and script fonts
- Publishing prices:
  - 50 Telegram Stars → 2 hours
  - 100 Telegram Stars → 15 hours
  - 200 Telegram Stars → permanent

## Media privacy
Telegram files are served through the WishVerse backend. The bot token is never exposed in the generated website HTML.

## Free publishing
- `OWNER_ID` publishes permanently for free.
- `/grantfree USER_ID` grants another user permanent free publishing.
- `/revokefree USER_ID` removes free publishing.

## Heroku
Scale:
- web = 1
- worker = 1

Required Config Vars:
- BOT_TOKEN
- OWNER_ID
- MONGO_URI
- BASE_URL
- SECRET_KEY
- PREVIEW_MINUTES=2
