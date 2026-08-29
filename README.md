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


## Fix in this version
This release fixes the preview/public website 500 error caused by MongoDB datetime timezone comparisons. Existing MongoDB records are supported too.


## Rich package update
### Normal (paid)
- Up to 4 photos
- Separate title and wish/message fonts
- Reveal surprise
- Secret message/letter
- Celebration/confetti effect
- Beautiful themes, animated effects and professional layouts

### Premium
- Up to 8 photos
- 1 video
- Larger premium font collection
- Multiple interactive experiences
- Reveal surprise, secret letter and celebration effect
- Rich gallery and premium media presentation


## Publish fix
This version fixes false "Website not found" errors when pressing Publish by:
- Looking up the website by slug first
- Checking ownership separately
- Supporting timezone-safe publish expiry checks
- Verifying the website update after a successful Telegram Stars payment


## Premium Interactive Theme Experience
Premium users now choose a complete website experience:
- Midnight Universe
- Luxury Birthday
- Romantic Love Story
- Soft Aesthetic
- Royal Luxury
- Party Celebration
- Memory Journey

Premium pages include an interactive journey structure with surprise cards, secret letter, make-a-wish interaction, clickable stars and cinematic finale. Normal package remains unchanged.
