#!/usr/bin/env bash
# AI yordamchini yoqish: Anthropic API kalitini serverdagi .env ga yozadi va botni qayta ishga tushiradi.
# Kalit ekranda ko'rinmaydi va hech qayerga (chat, git) yuborilmaydi.
# Ishlatish: bash /opt/uniccode/src/uniccode/deploy/setup_ai.sh
set -euo pipefail
ENVF=/opt/uniccode/.env
[ -f "$ENVF" ] || { echo "XATO: $ENVF yo'q - avval install.sh ni ishga tushiring"; exit 1; }
read -rsp "Anthropic API kaliti (sk-ant-...): " KEY; echo
case "$KEY" in sk-ant-*) ;; *) echo "XATO: kalit 'sk-ant-' bilan boshlanishi kerak"; exit 1;; esac
code=$(curl -s -o /dev/null -w '%{http_code}' https://api.anthropic.com/v1/models \
  -H "x-api-key: $KEY" -H "anthropic-version: 2023-06-01" || true)
if [ "$code" != "200" ]; then echo "XATO: kalit ishlamadi (HTTP $code)"; exit 1; fi
sed -i '/^ANTHROPIC_API_KEY=/d' "$ENVF"
echo "ANTHROPIC_API_KEY=$KEY" >> "$ENVF"
chmod 600 "$ENVF"
cd /opt/uniccode/src/uniccode/deploy
docker compose -p uniccode --env-file "$ENVF" up -d bot
echo ">> AI yoqildi. Bot loglarida 'AI yordamchi: yoqilgan' chiqishi kerak:"
sleep 8; docker logs uniccode-bot-1 2>&1 | grep -m1 "AI yordamchi" || true
