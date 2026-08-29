# WishVerse — Normal + Premium Website Maker

## Packages
### ✨ Normal (paid)
- Up to 4 photos
- Separate title and message fonts
- Animated/static background themes
- Reveal surprise
- Secret letter
- Celebration/confetti
- Telegram Stars publishing

### 💎 Premium (paid)
- Up to 8 photos
- 1 optional video
- Full interactive story website
- Category-specific Premium theme selection
- Each theme now has its own animated background scene: balloons, party, shooting stars, rose petals, neon hearts, romantic sky, golden sparkles, polaroid glow, bubbles, confetti, fireworks, mystic fog, magic portal, lanterns, fairy lights, aurora and more.
- Premium fonts and interactive chapters

## Publishing prices
### Normal
- 25 ⭐ → 2 hours
- 50 ⭐ → 15 hours
- 100 ⭐ → permanent

### Premium
- 50 ⭐ → 2 hours
- 100 ⭐ → 15 hours
- 200 ⭐ → permanent

## Owner commands
- `/grantfree USER_ID` — give permanent free publishing
- `/revokefree USER_ID` — remove free publishing
- `/freeusers` — list users with free access

## Required Heroku Config Vars
- `BOT_TOKEN`
- `OWNER_ID` — numeric Telegram user ID of the bot owner. Without this, owner commands will not work.
- `LOG_GROUP_ID` — optional numeric logger group ID, usually starting with `-100`
- `MONGO_URI`
- `BASE_URL` — full Heroku domain, for example `https://your-app.herokuapp.com`
- `SECRET_KEY`
- `PREVIEW_MINUTES=2`

## Telegram Stars
Payments use Telegram Stars with currency `XTR`. `provider_token` is intentionally empty for Stars. A website is published only after Telegram sends a verified `successful_payment` update and the payload/amount/user are checked.

## Logger group
Add the bot to your private logger group and set `LOG_GROUP_ID`. The bot logs successful payments, free publishing, granting access and revoking access.
