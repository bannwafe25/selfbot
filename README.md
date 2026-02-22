## What is a Telegram Selfbot?

A Telegram selfbot is essentially a script or program that logs into your *personal* Telegram account (not a bot account created via BotFather) and automates actions on your behalf. Think of it as giving your Telegram account superpowers by automating repetitive tasks or adding custom functionalities.

## Environment

- `MONGODB_URI` (required): MongoDB URI, e.g. `mongodb://localhost:27017/selfbot` or `mongodb+srv://...`
- `BOT_TOKEN` (required): Telegram bot token
- `GEMINI_API_KEY` (optional)
- `STICKER_FILE_ID` (optional)

`DATABASE_URL` is still accepted as a fallback, but it must contain a MongoDB URI.
