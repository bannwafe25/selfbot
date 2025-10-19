# Telegram Selfbot

A modular Telegram selfbot built with [PyroTgFork](https://github.com/TelegramPlayground/pyrogram) (Pyrogram fork) and PostgreSQL.

## Features

- 🔌 **Modular Architecture** - Easy to add/remove features
- 🗄️ **PostgreSQL Storage** - Persistent sessions and data
- 🎯 **Event-Driven** - Priority-based listener system
- 🔄 **Hot Reload** - Update code without losing sessions
- 🐳 **Docker Ready** - Deploy anywhere with containers
- ⚡ **Async/Await** - Fast and efficient operations

## Built-in Modules

| Module | Command | Description |
|--------|---------|-------------|
| **AFK** | `afk [reason]` | Auto-reply when mentioned |
| **Call** | `[action]call [options]` | Join/manage voice chats |
| **Debug** | `code#` or `e code` | Execute Python code |
| **Delete** | `d` or `del` | Delete messages |
| **GenAI** | `query !?` | Chat with Gemini AI |
| **Graph** | `graph [text] -t [title]` | Create Telegraph pages |
| **Help** | `help[/module]` | Show available commands |
| **Ping** | `p` or `ping` | Check bot latency |
| **Purge** | `purge[me] [limit]` | Bulk delete messages |
| **Restart** | `r` | Restart and update bot |

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL database
- Telegram API credentials ([get here](https://my.telegram.org))
- Bot token from [@BotFather](https://t.me/BotFather)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/DeltaUniverse/selfbot.git
   cd selfbot
   ```

2. **Install dependencies**
   ```bash
   pip install poetry
   poetry install
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

4. **Run the bot**
   ```bash
   poetry run python -m selfbot
   ```

### Docker Setup

```bash
# Build and run with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f selfbot

# Stop
docker-compose down
```

## Configuration

Create a `.env` file in the root directory:

```env
# Required
API_ID=your_api_id
API_HASH=your_api_hash
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# Optional
GEMINI_API_KEY=your_gemini_key  # For GenAI module
STICKER_FILE_ID=file_id         # Custom inline sticker
REMOTE=https://github.com/YourRepo/selfbot
BRANCH=main
```

## Usage Examples

### Basic Commands
```
# Check bot status
ping

# Get help
help
help/debug

# Delete messages
<reply to message> d
<reply to start> purge 50

# Execute code
print("Hello")#
e await app.send_message("me", "Test")
```

### AFK Mode
```
# Set AFK with reason
afk Working on something

# Remove AFK (same command)
afk
```

### AI Chat
```
# Ask Gemini
What is Telegram MTProto? !?

# With context (reply/quote to message)
<reply to message> Explain this !?
```

### Telegraph Pages
```
# Create page
graph Hello, World! -t My Page

# From replied message
<reply to message> graph -t Article Title
```

## Development

### Project Structure
```
selfbot/
├── core/           # Core components (database, dispatcher, etc.)
├── modules/        # Feature modules
├── utils/          # Helper functions
├── __init__.py
├── __main__.py
└── main.py         # Entry point
```

### Creating a Module

```python
from pyrogram import filters
from pyrogram.types import Message
from selfbot import listener
from selfbot.module import Module

class MyModule(Module):
    name = "MyModule"
    cmds = "mycommand {arg}"
    desc = {"arg": "Description", "e.g.": "mycommand test"}

    @listener.handler(filters.regex(r"^mycommand (.+)$"), priority=1)
    async def on_message_out(self, event: Message) -> None:
        arg = event.matches[0].group(1)
        await event.edit_text(f"You said: {arg}")
```

## Deployment

### Using Docker

```bash
# Production build
docker build -t selfbot:latest .
docker run -d --env-file .env selfbot:latest
```

### Using systemd

Create `/etc/systemd/system/selfbot.service`:

```ini
[Unit]
Description=Telegram Selfbot
After=network.target postgresql.service

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/selfbot
Environment="PATH=/path/to/selfbot/.venv/bin"
ExecStart=/path/to/selfbot/.venv/bin/python -m selfbot
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable selfbot
sudo systemctl start selfbot
```

## Troubleshooting

### Common Issues

**"Database connection failed"**
- Check `DATABASE_URL` format
- Ensure PostgreSQL is running
- Verify credentials and database exists

**"API_ID/API_HASH invalid"**
- Get new credentials from https://my.telegram.org
- Check for typos in `.env`

**"Module not loading"**
- Check module syntax and imports
- View logs: `docker-compose logs -f` or check console

**"Flood wait errors"**
- Telegram rate limits apply
- Bot auto-sleeps for small waits (<30s)
- For large operations, use `purge` with limits

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

**Note:** Focus on working features over perfect code. See `BACKLOG.md` for improvement ideas.

## License

MIT License - See [LICENSE](LICENSE) file for details.

## Disclaimer

This is a **selfbot** (user account automation), which is against [Telegram's Terms of Service](https://telegram.org/tos). Use at your own risk.

- ⚠️ Your account may be banned
- 🔒 Keep your credentials secure
- 🚫 Don't spam or abuse the API
- 👤 Use responsibly and ethically

**For educational purposes only.**

## Support

- 📖 Documentation: Check module docstrings and `help` command
- 🐛 Issues: [GitHub Issues](https://github.com/YourUsername/selfbot/issues)
- 💬 Discussions: [Telegram Discussions](https://t.me/deltaDiscuss)

---

**Version:** 2025.10.19
**Python:** 3.11+ | **Database:** PostgreSQL | **Framework:** PyroTgFork
