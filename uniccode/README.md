# @uniccodebot — unikal kodlarni SQL bazada yasash

Google Sheets'dagi "Уник код" generatorining o'rnini bosadi. Kodlar PostgreSQL'da yasaladi:
bitta kod millisekundlarda, 50 000 kod taxminan 1 soniyada. Har bir yangi kod alohida
Google Sheet'ga avtomatik yuklanadi.

Kod formati o'zgarmaydi: `844088` + `CA` + `0310` (kun, oy) + `10002897` = `844088CA031010002897`.

## Nima uchun takror kod chiqmaydi

- Har bir artikulning oxirgi raqami `uc_counters` jadvalida turadi. Raqamlar bitta atomar
  so'rov bilan band qilinadi, shuning uchun bir vaqtda o'n kishi so'rasa ham bir xil raqam chiqmaydi.
- `uc_codes.code` noyob ustun: bazaga bir xil kod ikki marta yozilmaydi.

## Buyruqlar

| Buyruq | Nima qiladi |
|---|---|
| `/kod 844088 5` | 844088 ga 5 ta kod. Izoh bilan: `/kod 844088 5 T535` |
| `/oxirgi 844088` | Oxirgi band raqam va oxirgi 5 ta kod |
| `/holat` | Bazadagi kodlar soni, Google Sheets'ga yuklanishi kutilayotganlar |
| `/import` | (admin) Eski bazani xlsx fayldan ko'chirish |

## Excel fayl yuborish

1. **1C sklad hisoboti** ("Движения товаров на адресных складах", .xls yoki .xlsx).
   Bot qatorlar bo'yicha qoldiqni ko'rsatadi va so'raydi: `9,1`, `TM_6D3, S_TM-Transit` yoki `hammasi`.
   Keyin "Hammasiga" yoki "Faqat chexol" tugmasini bosasiz. Kod soni = "Конечный остаток".
   "Faqat chexol" — nomi `C-`, `CY-`, `X-`, `D-`, `MG-`, `Prime-` bilan boshlanadigan, nakidka,
   torpedka, nezamerzayka va antifriz bo'lmagan mahsulotlar.
2. **Ro'yxat (seriya bilan)**. Birinchi qatorda sarlavha: `Артикул`, `Кол-во` majburiy;
   `Seria` (yoki `Серия`, `Партия`), `Адрес`, `Наименование`, `Izoh` ixtiyoriy.
   Sarlavhasiz fayl ham bo'ladi: A ustun artikul, B soni, C seriya.
   Seriya Датабаза'ning izoh ustuniga (E) yoziladi.

Bot har safar Excel qaytaradi: "Kodlar" varag'ining A:E ustunlari eski Датабаза formatida.

## Ishga tushirish

1. `.env` ga `uniccode/.env.example` dagi qatorlarni qo'shing va `UNIC_BOT_TOKEN` ni yozing.
   `UNIC_ADMIN_IDS` ga o'z Telegram ID'ingizni yozing (bot `/start` da ko'rsatadi).
   `UNIC_ALLOWED_IDS` ga kod yasashi mumkin bo'lgan xodimlar ID'sini yozing.
   Ikkalasi bo'sh bo'lsa bot hammaga ochiq bo'ladi.
2. Docker bilan: `docker compose up -d --build uniccode`.
   Docker'siz: `pip install -r requirements.txt` va `python -m uniccode`.
3. Jadvallar (`uc_counters`, `uc_codes`, `uc_batches`) birinchi ishga tushishda o'zi yaratiladi.
   Asosiy Taskbot jadvallariga tegmaydi.

## Serverga o'rnatish (Ubuntu/Debian, bitta buyruq)

Serverga root bilan kirib, shu buyruqni bering:

```bash
curl -fsSL https://raw.githubusercontent.com/Abduvohiddev/Taskbot.uz/claude/gifted-knuth-095ih4/uniccode/deploy/install.sh | bash
```

Skript Docker'ni o'rnatadi, kodni `/opt/uniccode/src` ga yuklaydi, bot tokeni va admin ID'ni so'raydi,
`/opt/uniccode/.env` ni yaratadi (PostgreSQL paroli tasodifiy) va botni o'z bazasi bilan ishga tushiradi.
Bot va baza server qayta yonganda o'zi ko'tariladi. Shu buyruqni qayta bersangiz kod yangilanadi,
`.env` va baza saqlanadi.

- Loglar: `docker logs -f --tail 50 uniccode-bot-1`
- Sozlamani o'zgartirish: `/opt/uniccode/.env` ni tahrirlab, skriptni qayta ishga tushiring.
- Google kaliti: `/opt/uniccode/secrets/google.json` ga qo'yib, skriptni qayta ishga tushiring.

## Eski bazadan o'tish (bir marta)

1. Google Sheets'da hamma "Уник код" orqali kod yasashni to'xtatadi.
2. Jadvalni **Файл → Скачать → Microsoft Excel (.xlsx)** qilib yuklab oling.
3. Botga `/import` yozib, faylni yuboring. 263 ming qatorli baza 1-2 daqiqada ko'chadi.
   Bor kodlar takror yozilmaydi, hisoblagich har bir artikulning eng katta raqamiga ko'tariladi.
   Faylni qayta yuborish xavfsiz.
4. Shundan keyin kodlar **faqat bot orqali** yasaladi. Google Sheets'dagi generatorda ham kod
   yasashda davom etilsa, ikkala tizim bir xil raqamlarni beradi.

Telegram botlar 20 MB dan katta faylni yuklab ololmaydi. Baza shundan oshsa, eski yillarni
alohida faylga ajratib, bir necha marta import qiling.

## Google Sheets'ga real vaqtda yuklash

1. [Google Cloud Console](https://console.cloud.google.com/) da loyiha oching va
   **Google Sheets API** ni yoqing.
2. **IAM → Service accounts** da service account yarating, unga **JSON kalit** yarating va yuklab oling.
3. Faylni serverda `secrets/google.json` ga qo'ying (`secrets/` git'ga tushmaydi).
4. Yangi Google Sheet oching va uni service account email'iga (`...@...iam.gserviceaccount.com`)
   **Редактор** huquqi bilan ulashing.
5. `.env` ga yozing: `GSHEET_ID` (havoladagi `/d/` va `/edit` orasidagi qism) va
   `GOOGLE_CREDENTIALS_FILE=/app/secrets/google.json`.

Bot har 15 soniyada yangi kodlarni `Kodlar` varag'i oxiriga qo'shadi (bitta so'rovda 5000 tagacha).
Google ishlamay qolsa, kodlar bazada kutib turadi va keyingi urinishda yuklanadi; kod yasash to'xtamaydi.
Import qilingan eski kodlar Sheets'ga qayta yuklanmaydi, chunki ular eski jadvalda bor.

## Testlar

```bash
pip install aiosqlite pytest
pytest tests/test_uniccode.py
```
