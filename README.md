# TaskBot 🤖

Korporativ vazifalar boshqaruvi Telegram bot — @utaskbot, @iTasksBot ga o'xshash, ammo to'liq bepul va ochiq kodli.

## ✨ Imkoniyatlar

- ✅ Vazifalar yaratish, tahrirlash, o'chirish
- ✅ Guruh/jamoa ichida ishlash
- ✅ Deadline kuzatish va avtomatik ogohlantirish
- ✅ Status tizimi (Yangi → Jarayonda → Ko'rilmoqda → Bajarildi)
- ✅ Kechikkan vazifalarni chart bilan ko'rsatish
- ✅ Statistika va batafsil hisobotlar
- ✅ 4 xil rol (Super admin, Admin, Menejer, Ijrochi)
- ✅ 3 til (O'zbek, Rus, Ingliz)
- ✅ Kunlik avtomatik hisobotlar
- ✅ Docker bilan oson ishga tushirish

## 🛠 Texnologiyalar

- **Python 3.11+** — asosiy til
- **aiogram 3** — Telegram bot framework
- **PostgreSQL 16** — ma'lumotlar bazasi
- **Redis 7** — kesh va FSM holat
- **SQLAlchemy 2.0** — async ORM
- **APScheduler** — rejalashtiruvchi
- **Matplotlib** — chart generatsiyasi
- **Docker + Docker Compose** — konteynerlashtirish

## 🚀 Ishga tushirish

### 1. Loyihani klonlash

```bash
git clone https://github.com/username/taskbot.git
cd taskbot
```

### 2. Environment sozlash

`.env.example` ni `.env` ga nusxalang va to'ldiring:

```bash
cp .env.example .env
nano .env
```

Asosiy o'zgaruvchilar:

```env
BOT_TOKEN=your_bot_token_from_botfather
ADMIN_IDS=123456789,987654321
```

Bot tokenini [@BotFather](https://t.me/BotFather) dan oling.

### 3. Docker bilan ishga tushirish (tavsiya)

```bash
docker-compose up -d
```

Loglarni ko'rish:
```bash
docker-compose logs -f bot
```

To'xtatish:
```bash
docker-compose down
```

### 4. Lokal ishga tushirish (Docker siz)

PostgreSQL va Redis lokalda ishlab turishi kerak.

```bash
pip install -r requirements.txt
python bot.py
```

## 📁 Loyiha strukturasi

```
taskbot/
├── bot.py                  # Asosiy fayl
├── config.py               # Sozlamalar
├── database/
│   ├── models.py           # 8 ta jadval
│   └── db.py               # Async ulanish
├── handlers/
│   ├── start.py            # /start, til tanlash
│   ├── tasks.py            # Vazifalar CRUD (FSM)
│   ├── groups.py           # Guruh boshqaruvi
│   ├── stats.py            # Statistika + chart
│   ├── admin.py            # Super admin panel
│   └── common.py           # Sozlamalar, filtrlash
├── middlewares/
│   ├── auth.py             # Foydalanuvchi tekshiruv
│   └── throttling.py       # Spam himoyasi
├── keyboards/
│   ├── inline.py           # Inline tugmalar
│   └── reply.py            # Reply klaviaturalar
├── services/
│   ├── task_service.py     # Vazifa biznes logika
│   ├── group_service.py    # Guruh xizmati
│   ├── notification_service.py
│   └── stats_service.py
└── utils/
    ├── charts.py           # Matplotlib chartlar
    ├── scheduler.py        # APScheduler
    └── helpers.py          # Yordamchilar
```

## 🤖 Bot buyruqlari

| Buyruq | Ta'rif | Kim ishlatadi |
|--------|--------|---------------|
| `/start` | Botni ishga tushirish | Hamma |
| `/newtask` | Yangi vazifa yaratish | Menejer, Admin |
| `/mytasks` | Mening vazifalarim | Hamma |
| `/alltasks` | Barcha vazifalar | Menejer, Admin |
| `/task_<id>` | Vazifa tafsilotlari | Ruxsatli |
| `/comment_<id>` | Izoh yozish | Ruxsatli |
| `/stats` | Statistika va chart | Hamma |
| `/overdue` | Kechikkan vazifalar | Menejer, Admin |
| `/report` | Haftalik hisobot | Admin |
| `/members` | Guruh a'zolari | Hamma |
| `/settings` | Shaxsiy sozlamalar | Hamma |
| `/help` | Yordam | Hamma |
| `/admin` | Super admin panel | Super admin |

## 👥 Rollar

### Super admin
- Tizim darajasidagi barcha huquqlar
- Foydalanuvchilarni bloklash/tiklash
- Broadcast xabarlar
- Umumiy statistika

### Guruh admin
- Guruhni to'liq boshqarish
- A'zolar qo'shish/o'chirish
- Rollarni o'zgartirish
- Barcha vazifalarni ko'rish

### Menejer
- Vazifa yaratish
- Boshqa a'zolarga biriktirish
- Vazifalarni tekshirish (review)
- Izoh qoldirish

### Ijrochi
- O'ziga biriktirilgan vazifalar
- Statusni yangilash
- Izoh yozish

## 📊 Chart turlari

Bot matplotlib yordamida 4 xil chart generatsiya qiladi:

1. **Pie chart** — vazifalar statusi taqsimoti
2. **Bar chart** — a'zolar bo'yicha bajarilish va kechikishlar
3. **Line chart** — haftalik dinamika
4. **Kompleks hisobot** — barcha chartlar birga

## ⏰ Avtomatik bildirishnomalar

Scheduler har soatda tekshiradi:

- **24 soat qolsada** — ijrochiga eslatma
- **1 soat qolsada** — favqulodda ogohlantirish
- **Deadline o'tsa** — avtomatik "Kechikdi" statusi va admin ga xabar
- **Har kuni 09:00** — admin guruhga kunlik hisobot (chart bilan)

## 🔒 Xavfsizlik

- Barcha parollar `.env` faylda
- SQL injection himoyasi (SQLAlchemy)
- Rate limiting (throttling middleware)
- Bloklangan foydalanuvchilar
- Audit log (task_history)

## 🧪 Testlash

```bash
pytest tests/
```

## 📝 Migratsiya (Alembic)

Yangi DB o'zgarishlar uchun:

```bash
alembic revision --autogenerate -m "Description"
alembic upgrade head
```

## 💾 Backup

```bash
# Qo'lda backup
docker-compose exec postgres pg_dump -U taskbot taskbot > backup.sql

# Tiklash
docker-compose exec -T postgres psql -U taskbot taskbot < backup.sql
```

## 📞 Qo'llab-quvvatlash

- **Issue**: GitHub issues orqali
- **Email**: support@taskbot.uz
- **Telegram**: @taskbot_support

## 📄 Litsenziya

MIT License — to'liq ochiq kodli, o'zgartirib ishlatish mumkin.

## 🙏 Minnatdorchilik

- [aiogram](https://github.com/aiogram/aiogram) — zamonaviy Telegram bot framework
- [SQLAlchemy](https://www.sqlalchemy.org/) — eng yaxshi Python ORM
- Barcha ochiq kod kutubxonalari mualliflariga

---

**Made with ❤️ in Uzbekistan**
"# Taskbot.uz" 
