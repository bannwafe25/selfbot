# bannwafe25/selfbot

Telegram selfbot (bot account via BotFather) — modular, MongoDB-backed.

## Stack

- Python 3.12–3.14, [Kurigram](https://github.com/KurimuzonAkuma/pyrogram) (Pyrogram fork)
- `uv` untuk dependency management
- MongoDB (Atlas / lokal)
- systemd service `tg-selfbot`

## Deploy VPS baru

```bash
bash deploy.sh
```

Script otomatis: clone/update repo ke `~/apps/selfbot`, `uv sync`, cek ffmpeg+node, pasang systemd service, start.

Yang harus diisi manual: `.env` (script nge-prompt waktu pertama). Lihat `.env.example`.

Panduan lengkap step-by-step: [docs/DEPLOY.txt](docs/DEPLOY.txt)

## Environment

| Var | Wajib | Fungsi |
|---|---|---|
| `MONGODB_URI` | ya | MongoDB connection string |
| `BOT_TOKEN` | ya | Token bot dari @BotFather |
| `ARC_API_KEY` | modul music | api.arcmusic.fun |
| `XKIRO_API_KEY` | modul genai | OpenAI-compatible endpoint (qwen) |
| `GEMINI_API_KEY` | fallback genai | aistudio.google.com |
| `LOG_GROUP` | opsional | grup log untuk foto profil (`info`) |
| `AI_API_KEY`, `STICKER_FILE_ID` | opsional | — |

`DATABASE_URL` masih diterima sebagai fallback, tapi harus berisi MongoDB URI.

## Struktur

```
selfbot/
  modules/    # 1 file = 1 module, auto-discovered
  core/       # client, database, telegram
  methods/    # helper methods injected ke module
deploy.sh     # one-command deploy
run.sh        # manual run (load .env + uv run)
```

## Develop

- Edit module di `selfbot/modules/`, deploy: `cp <file> ~/apps/selfbot/selfbot/modules/` lalu `sudo systemctl restart tg-selfbot`
- Syntax check: `cd ~/selfbot && set -a && source ~/apps/selfbot/.env && set +a && uv run python -c 'import selfbot.modules.<name>'`
- yt-dlp di-pin `>=2026.8.19` — jangan diturunin (SABR 403 / bot-check)
