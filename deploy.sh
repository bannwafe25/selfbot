#!/usr/bin/env bash
# ============================================================
# Deploy otomatis Selfbot (github.com/bannwafe25/selfbot)
# Pakai: bash deploy.sh
# ============================================================
set -e

APP_DIR="$HOME/apps/selfbot"
SERVICE_NAME="tg-selfbot"

echo "==> [1/6] Cek dependencies..."
if ! command -v git &>/dev/null; then
    echo "git tidak ada. Install dulu: sudo apt install -y git"
    exit 1
fi
if ! command -v uv &>/dev/null; then
    echo "==> uv belum ada, installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "==> [2/6] Clone / update repo..."
if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR"
    git pull origin staging
else
    mkdir -p "$HOME/apps"
    git clone https://github.com/bannwafe25/selfbot.git "$APP_DIR"
    cd "$APP_DIR"
fi

echo "==> [3/6] Install dependencies..."
uv sync

echo "==> [4/6] Cek file .env..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "!!! .env baru dibuat. ISI DULU:"
    echo "    nano $APP_DIR/.env"
    echo "    (MONGODB_URI, BOT_TOKEN, GEMINI_API_KEY)"
    echo "    lalu jalankan lagi: bash deploy.sh"
    exit 1
fi

echo "==> [5/6] Pasang systemd service..."
sudo tee /etc/systemd/system/$SERVICE_NAME.service >/dev/null <<EOF
[Unit]
Description=TG Selfbot
After=network-online.target

[Service]
WorkingDirectory=$APP_DIR
ExecStart=$HOME/.local/bin/uv run selfbot
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload

echo "==> [6/6] Start service..."
sudo systemctl enable --now $SERVICE_NAME
sleep 8
sudo systemctl restart $SERVICE_NAME
sleep 45

if systemctl is-active --quiet $SERVICE_NAME; then
    echo ""
    echo "✅ DEPLOY BERHASIL! Selfbot aktif."
    echo "   Log live: journalctl -u $SERVICE_NAME -f"
else
    echo ""
    echo "❌ Service belum aktif. Cek log:"
    echo "   journalctl -u $SERVICE_NAME -n 30"
fi
