#!/usr/bin/env bash
# @uniccodebot ni 1C OData ga ulash: login/parolni so'raydi, ulanishni tekshiradi, .env ga yozadi,
# botni yangilaydi va katalogni darhol 1C dan yuklab, natijani ko'rsatadi. Root sifatida:
#   curl -fsSL https://raw.githubusercontent.com/Abduvohiddev/Taskbot.uz/claude/gifted-knuth-095ih4/uniccode/deploy/setup_1c.sh | bash
set -euo pipefail
ENVF=/opt/uniccode/.env
URL_DEFAULT="http://185.203.239.37/ERP25/odata/standard.odata/"
ENTITY_ENC="Catalog_%D0%9D%D0%BE%D0%BC%D0%B5%D0%BD%D0%BA%D0%BB%D0%B0%D1%82%D1%83%D1%80%D0%B0"

[ "$(id -u)" = 0 ] || { echo "root sifatida ishga tushiring"; exit 1; }
[ -f $ENVF ] || { echo "$ENVF topilmadi - avval install.sh ni ishga tushiring"; exit 1; }

URL="${ONEC_BASE_URL:-}"
[ -n "$URL" ] || { read -rp "1C OData manzili [$URL_DEFAULT]: " URL </dev/tty; URL="${URL:-$URL_DEFAULT}"; }
URL="${URL%/}/"
USR="${ONEC_USER:-}"
[ -n "$USR" ] || read -rp "1C login: " USR </dev/tty
PSW="${ONEC_PASSWORD:-}"
[ -n "$PSW" ] || { read -rsp "1C parol (yozilganda ko'rinmaydi): " PSW </dev/tty; echo; }
case "$USR$PSW" in *"'"*) echo "!! Login yoki parolda ' belgisi bor - .env ga qo'lda yozing."; exit 1 ;; esac

echo ">> 1C ga ulanish tekshirilmoqda..."
CODE=$(curl -s -o /tmp/uc_1c_test.json -w "%{http_code}" -m 60 -u "$USR:$PSW" \
  "${URL}${ENTITY_ENC}?\$top=1&\$format=json" || true)
case "$CODE" in
  200) echo ">> 1C javob berdi (200)." ;;
  401) echo "!! Login yoki parol noto'g'ri (401). Qaytadan ishga tushiring."; exit 1 ;;
  000) echo "!! 1C serveriga ulanib bo'lmadi: bu VPS dan $URL ochiq emas (firewall) yoki 1C o'chiq."; exit 1 ;;
  *)   echo "!! 1C xato qaytardi: HTTP $CODE"; head -c 300 /tmp/uc_1c_test.json; echo; exit 1 ;;
esac
rm -f /tmp/uc_1c_test.json

# Eski ONEC_ qatorlarini almashtiramiz
sed -i '/^ONEC_/d' $ENVF
{
  printf 'ONEC_BASE_URL=%s\n' "$URL"
  printf "ONEC_USER='%s'\n" "$USR"        # bir tirnoq: Docker $ va boshqa belgilarni o'zgartirmaydi
  printf "ONEC_PASSWORD='%s'\n" "$PSW"
  printf 'ONEC_SYNC_INTERVAL_HOURS=24\n'
} >> $ENVF
chmod 600 $ENVF
echo ">> $ENVF yangilandi."

echo ">> Bot yangilanmoqda..."
curl -fsSL https://raw.githubusercontent.com/Abduvohiddev/Taskbot.uz/claude/gifted-knuth-095ih4/uniccode/deploy/install.sh | bash >/tmp/uc_install.log 2>&1 \
  || { echo "!! O'rnatishda xato:"; tail -20 /tmp/uc_install.log; exit 1; }
sleep 5

echo ">> Katalog 1C dan yuklanmoqda (1-2 daqiqa)..."
docker exec uniccode-bot-1 python -c '
import asyncio
from uniccode.config import unic_settings as cfg
from uniccode.db import make_engine, make_sessionmaker, init_db
from uniccode.bot import sync_catalog_from_1c
async def main():
    e = make_engine(cfg.database_url); await init_db(e)
    try:
        n = await sync_catalog_from_1c(make_sessionmaker(e), cfg)
        print(f"OK: katalog 1C dan yangilandi - {n} ta artikul")
    except Exception as ex:
        print(f"XATO: {ex}")
    finally:
        await e.dispose()
asyncio.run(main())
'
echo ">> Tayyor. Bundan keyin bot katalogni har 24 soatda o'zi yangilaydi; Telegram'da /katalog_1c - darhol yangilash."
