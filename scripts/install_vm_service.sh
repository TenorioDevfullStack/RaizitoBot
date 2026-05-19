#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE_NAME="${SERVICE_NAME:-raizitobot}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="${RUN_USER:-${SUDO_USER:-$(id -un)}}"

if [[ "$RUN_USER" == "root" && -n "${RAIZITOBOT_USER:-}" ]]; then
    RUN_USER="$RAIZITOBOT_USER"
fi

if [[ ! -f "$REPO_DIR/.env" ]]; then
    echo "Arquivo .env nao encontrado em $REPO_DIR." >&2
    echo "Crie o .env a partir de .env.example antes de instalar o servico." >&2
    exit 1
fi

if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip ffmpeg git
fi

chmod +x "$REPO_DIR/start_bot.sh"
"$REPO_DIR/start_bot.sh" --prepare-only

mkdir -p "$REPO_DIR/data" "$REPO_DIR/logs"
sudo chown -R "$RUN_USER:$RUN_USER" "$REPO_DIR/data" "$REPO_DIR/logs"
sudo chmod -R u+rwX "$REPO_DIR/data" "$REPO_DIR/logs"

sudo tee "/etc/systemd/system/${SERVICE_NAME}.service" >/dev/null <<SERVICE
[Unit]
Description=RaizitoBot Telegram bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${REPO_DIR}
ExecStart=${REPO_DIR}/start_bot.sh
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"

echo "Servico ${SERVICE_NAME} instalado e iniciado."
echo "Logs: sudo journalctl -u ${SERVICE_NAME} -f"
