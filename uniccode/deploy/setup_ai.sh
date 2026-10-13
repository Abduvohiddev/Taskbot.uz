#!/usr/bin/env bash
# AI yordamchini yoqish: API kalitini serverdagi .env ga yozadi va botni qayta ishga tushiradi.
# Kalit ekranda ko'rinmaydi va hech qayerga (chat, git) yuborilmaydi.
# Ishlatish:
#   bash /opt/uniccode/src/uniccode/deploy/setup_ai.sh          # Google Gemini (odatiy)
#   bash /opt/uniccode/src/uniccode/deploy/setup_ai.sh claude   # Anthropic Claude
set -euo pipefail
ENVF=/opt/uniccode/.env
PROVIDER=${1:-gemini}
[ -f "$ENVF" ] || { echo "XATO: $ENVF yo'q - avval install.sh ni ishga tushiring"; exit 1; }

if [ "$PROVIDER" = "gemini" ]; then
  echo "Gemini API kaliti: https://aistudio.google.com/apikey -> Create API key"
  read -rsp "Gemini API kaliti: " KEY; echo
  KEY=$(echo "$KEY" | tr -d '[:space:]')
  [ -n "$KEY" ] || { echo "XATO: kalit bo'sh"; exit 1; }
  code=$(curl -s -o /dev/null -w '%{http_code}' "https://generativelanguage.googleapis.com/v1beta/models" \
    -H "x-goog-api-key: $KEY" || true)
  [ "$code" = "200" ] || { echo "XATO: kalit ishlamadi (HTTP $code). Kalitni qayta nusxalab ko'ring."; exit 1; }
  VAR=GEMINI_API_KEY
elif [ "$PROVIDER" = "claude" ]; then
  read -rsp "Anthropic API kaliti (sk-ant-...): " KEY; echo
  KEY=$(echo "$KEY" | tr -d '[:space:]')
  code=$(curl -s -o /dev/null -w '%{http_code}' https://api.anthropic.com/v1/models \
    -H "x-api-key: $KEY" -H "anthropic-version: 2023-06-01" || true)
  [ "$code" = "200" ] || { echo "XATO: kalit ishlamadi (HTTP $code)"; exit 1; }
  VAR=ANTHROPIC_API_KEY
else
  echo "Ishlatish: setup_ai.sh [gemini|claude]"; exit 1
fi

sed -i "/^$VAR=/d; /^UNIC_AI_PROVIDER=/d" "$ENVF"
echo "$VAR=$KEY" >> "$ENVF"
echo "UNIC_AI_PROVIDER=$PROVIDER" >> "$ENVF"
chmod 600 "$ENVF"
cd /opt/uniccode/src/uniccode/deploy
docker compose -p uniccode --env-file "$ENVF" up -d bot
echo ">> AI yoqildi ($PROVIDER). Bot logi:"
sleep 8; docker logs uniccode-bot-1 2>&1 | grep "AI yordamchi" | tail -1 || true
