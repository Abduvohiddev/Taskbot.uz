# TaskBot tez boshlash qo'llanmasi

Ushbu qo'llanma sizga botni 10 daqiqada ishga tushirishga yordam beradi.

## 1-qadam: Bot yaratish

1. Telegramda [@BotFather](https://t.me/BotFather) ga yozing
2. `/newbot` buyrug'ini yuboring
3. Bot nomini kiriting, masalan: "My TaskBot"
4. Username kiriting: `my_taskbot` (oxirida `bot` so'zi bo'lishi shart)
5. BotFather sizga token beradi — uni saqlang!

## 2-qadam: Botga huquqlar berish

BotFather da:
- `/setprivacy` → botingiz → **Disable** (guruhda barcha xabarlarni ko'ra olishi uchun)
- `/setjoingroups` → botingiz → **Enable** (guruhlarga qo'shila olishi uchun)
- `/setcommands` → botingiz → quyidagi buyruqlar ro'yxatini yuboring:

```
start - Botni ishga tushirish
newtask - Yangi vazifa yaratish
mytasks - Mening vazifalarim
alltasks - Barcha vazifalar
stats - Statistika va chart
overdue - Kechikkan vazifalar
report - Haftalik hisobot
members - A'zolar ro'yxati
settings - Sozlamalar
help - Yordam
```

## 3-qadam: Serverni tayyorlash

### Variant A: Docker (oson)

```bash
sudo apt update
sudo apt install docker.io docker-compose -y
```

### Variant B: Lokal o'rnatish

```bash
sudo apt install python3.11 python3-pip postgresql redis-server -y
```

## 4-qadam: Loyihani sozlash

```bash
git clone <repository_url> taskbot
cd taskbot

cp .env.example .env
nano .env
```

`.env` faylini shunday to'ldiring:

```env
BOT_TOKEN=6123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
BOT_USERNAME=my_taskbot

DATABASE_URL=postgresql+asyncpg://taskbot:taskbot_password@postgres:5432/taskbot
REDIS_URL=redis://redis:6379/0

ADMIN_IDS=YOUR_TELEGRAM_ID

DEFAULT_TIMEZONE=Asia/Tashkent
DEFAULT_LANGUAGE=uz
```

**Sizning Telegram ID ni bilish uchun:** [@userinfobot](https://t.me/userinfobot) ga /start yuboring.

## 5-qadam: Ishga tushirish

### Docker bilan:

```bash
docker-compose up -d
docker-compose logs -f bot
```

Natija:
```
taskbot_bot | Bot @my_taskbot muvaffaqiyatli ishga tushdi!
```

### Lokal:

```bash
pip install -r requirements.txt

sudo -u postgres createdb taskbot
sudo -u postgres psql -c "CREATE USER taskbot WITH PASSWORD 'taskbot_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE taskbot TO taskbot;"

python bot.py
```

## 6-qadam: Botni sinab ko'rish

1. Telegramda botingizni toping: `@my_taskbot`
2. `/start` yuboring
3. "➕ Yangi vazifa" tugmasini bosing
4. FSM orqali bosqichma-bosqich vazifa yarating
5. `/stats` yuboring — chart ko'rasiz

## 7-qadam: Guruhda ishlatish

1. Botni istalgan guruhga qo'shing
2. Botni guruh admin qiling (muhim!)
3. Guruhda `/newtask` yuboring
4. A'zolarga vazifa taqsimlang
5. `/stats` — guruh statistikasi

## Qo'shimcha sozlamalar

### Serverda fonda ishlashi uchun systemd

```bash
sudo nano /etc/systemd/system/taskbot.service
```

```ini
[Unit]
Description=TaskBot Telegram Bot
After=network.target docker.service

[Service]
Type=simple
WorkingDirectory=/opt/taskbot
ExecStart=/usr/bin/docker-compose up
ExecStop=/usr/bin/docker-compose down
Restart=always
User=ubuntu

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable taskbot
sudo systemctl start taskbot
```

### Loglar ko'rish

```bash
docker-compose logs -f --tail 100 bot
```

### DB ga kirish

```bash
docker-compose exec postgres psql -U taskbot taskbot
```

Foydali so'rovlar:
```sql
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM tasks GROUP BY status;
SELECT name, COUNT(m.id) FROM groups g LEFT JOIN group_members m ON g.id = m.group_id GROUP BY g.id, g.name;
```

### Backup qilish

Kunlik avtomatik backup uchun cron:

```bash
crontab -e
```

Qo'shing:
```
0 3 * * * cd /opt/taskbot && docker-compose exec -T postgres pg_dump -U taskbot taskbot > /opt/taskbot/backups/backup_$(date +\%Y\%m\%d).sql
```

## Muammolarni hal qilish

### Bot ishga tushmayapti

```bash
docker-compose logs bot | tail -50
```

Tez-tez uchraydigan xatolar:
- **"Invalid token"** — BOT_TOKEN noto'g'ri
- **"connection refused"** — PostgreSQL yoki Redis ishlamayapti
- **"ModuleNotFoundError"** — `pip install -r requirements.txt` bajaring

### Chart ishlamayapti

```bash
docker-compose exec bot python -c "import matplotlib; print(matplotlib.__version__)"
```

Agar xato bo'lsa:
```bash
docker-compose exec bot pip install --upgrade matplotlib
```

### Bildirishnomalar kelmayapti

1. `/settings` da bildirishnoma yoqilganligini tekshiring
2. Scheduler loglarini ko'ring:
```bash
docker-compose logs bot | grep -i scheduler
```

## Yangilanishlar

```bash
cd /opt/taskbot
git pull
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## Qo'shimcha yordam

- **Issues**: GitHub repository
- **Hujjatlar**: `/docs` papkasida
- **Kod**: to'liq kommentlar bilan

Omad!
