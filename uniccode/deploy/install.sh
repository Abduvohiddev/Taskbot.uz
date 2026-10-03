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
GSHEET_ID_DEFAULT="18_qi709DhAAbQfTgUUI2naNF1M3yBDmhfd_Ip2esrbM"

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
GSHEET_WORKSHEET=Kodlar
GOOGLE_CREDENTIALS_FILE=/app/secrets/google.json
GSHEET_SYNC_INTERVAL=15
EOV
  echo ">> $ENVF yaratildi"
fi

chown -R 1000:1000 $BASE/secrets 2>/dev/null || true
chmod 700 $BASE/secrets

cd $SRC/uniccode/deploy
docker compose -p uniccode --env-file $ENVF up -d --build
sleep 8
docker compose -p uniccode --env-file $ENVF ps
echo
echo ">> Tayyor. Loglar: docker logs -f --tail 50 uniccode-bot-1"
[ -f $BASE/secrets/google.json ] || echo ">> Google Sheets uchun service account kalitini $BASE/secrets/google.json ga qo'ying va shu skriptni qayta ishga tushiring."
