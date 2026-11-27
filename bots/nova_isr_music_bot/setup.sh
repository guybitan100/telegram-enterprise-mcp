#!/bin/bash
set -eu
cd "$(dirname "$0")"
command -v ffmpeg >/dev/null || { echo 'Install FFmpeg: brew install ffmpeg'; exit 1; }
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
if [ ! -f .env ]; then
 read -rsp 'Bot token: ' token; echo
 read -rp 'Your numeric Telegram user ID: ' uid
 [[ "$uid" =~ ^[0-9]+$ ]] || exit 1
 [[ "$token" =~ ^[0-9]+:[A-Za-z0-9_-]+$ ]] || exit 1
 umask 077; printf 'BOT_TOKEN=%s\nADMIN_ID=%s\n' "$token" "$uid" > .env
fi
exec .venv/bin/python bot.py
