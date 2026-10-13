#!/usr/bin/env bash
# @uniccodebot ni serverga o'rnatish yoki yangilash. Root sifatida ishga tushiring:
#   curl -fsSL https://raw.githubusercontent.com/Abduvohiddev/Taskbot.uz/claude/gifted-knuth-095ih4/uniccode/deploy/install.sh | bash
# Qayta ishga tushirsa: kodni yangilaydi va botni qayta ko'taradi (.env va baza saqlanadi).
set -euo pipefail

REPO="https://github.com/Abduvohiddev/Taskbot.uz.git"
BRANCH="${UNIC_BRANCH:-claude/gifted-knuth-095ih4}"
BASE=/opt/uniccode
SRC=$BASE/src
ENVF=$BASE/.env
GSHEET_ID_DEFAULT="1v53dHTGttiBmjBD1dgjfLNdi9ApDrYuEGdCvHon44TQ"

[ "$(id -u)" = 0 ] || { echo "root sifatida ishga tushiring"; exit 1; }

if ! command -v docker >/dev/null 2>&1; then
  echo ">> Docker o'rnatilmoqda..."
  curl -fsSL https://get.docker.com | sh
fi
command -v git >/dev/null 2>&1 || { apt-get update -y && apt-get install -y git; }
systemctl enable --now docker >/dev/null 2>&1 || true

mkdir -p $BASE/secrets
if [ -d $SRC/.git ]; then
  echo ">> Kod yangilanmoqda ($BRANCH)..."
  git -C $SRC fetch -q origin "$BRANCH" && git -C $SRC checkout -q -B "$BRANCH" "origin/$BRANCH"
else
  echo ">> Kod yuklanmoqda ($BRANCH)..."
  git clone -q --depth 1 -b "$BRANCH" "$REPO" $SRC
fi

if [ ! -f $ENVF ]; then
  echo ">> Birinchi o'rnatish: sozlamalar"
  TOKEN="${UNIC_BOT_TOKEN:-}"
  [ -n "$TOKEN" ] || read -rp "BotFather tokeni (@uniccodebot): " TOKEN </dev/tty
  ADMINS="${UNIC_ADMIN_IDS:-}"
  [ -n "$ADMINS" ] || read -rp "Admin Telegram ID (vergul bilan, bo'sh qoldirsa keyin qo'shasiz): " ADMINS </dev/tty
  PGPASS=$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24)
  umask 077
  cat > $ENVF <<EOV
UNIC_BOT_TOKEN=$TOKEN
UNIC_ADMIN_IDS=$ADMINS
UNIC_ALLOWED_IDS=
UNIC_TYPE_CODE=CA
UNIC_START_SEQ=10000000
UNIC_TZ=Asia/Tashkent
POSTGRES_PASSWORD=$PGPASS
GSHEET_ID=${GSHEET_ID:-$GSHEET_ID_DEFAULT}
GSHEET_WORKSHEET=Hammasi
GOOGLE_CREDENTIALS_FILE=/app/secrets/google.json
GSHEET_SYNC_INTERVAL=15
EOV
  echo ">> $ENVF yaratildi"
fi

# Admin panel: serverdagi bo'sh port (8090 band bo'lsa keyingisi), manzil va sessiya kaliti.
# Port bir marta tanlanadi va .env da qoladi (qayta ishga tushirganda o'zgarmaydi).
if ! grep -q '^PANEL_HOST_PORT=' $ENVF; then
  docker compose -p uniccode stop bot >/dev/null 2>&1 || true
  PORT=""
  for p in 8090 8091 8092 8093 8094 8095 8096 8097 8098 8099 18090; do
    if ! ss -ltnH 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$p\$"; then PORT=$p; break; fi
  done
  [ -n "$PORT" ] || { echo "XATO: 8090-8099 portlarining hammasi band"; exit 1; }
  echo "PANEL_HOST_PORT=$PORT" >> $ENVF
  sed -i '/^PANEL_URL=/d' $ENVF
  echo ">> Admin panel porti: $PORT"
fi
PANEL_HOST_PORT=$(grep '^PANEL_HOST_PORT=' $ENVF | tail -1 | cut -d= -f2)
grep -q '^PANEL_URL=' $ENVF || echo "PANEL_URL=http://$(hostname -I | awk '{print $1}'):$PANEL_HOST_PORT" >> $ENVF
grep -q '^PANEL_SECRET=' $ENVF || echo "PANEL_SECRET=$(openssl rand -hex 32)" >> $ENVF
command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active" && ufw allow "$PANEL_HOST_PORT"/tcp >/dev/null || true

chown -R 1000:1000 $BASE/secrets 2>/dev/null || true
chmod 700 $BASE/secrets

cd $SRC/uniccode/deploy
docker compose -p uniccode --env-file $ENVF up -d --build
sleep 8
docker compose -p uniccode --env-file $ENVF ps
echo
echo ">> Tayyor. Loglar: docker logs -f --tail 50 uniccode-bot-1"
[ -f $BASE/secrets/google.json ] || echo ">> Google Sheets uchun service account kalitini $BASE/secrets/google.json ga qo'ying va shu skriptni qayta ishga tushiring."
