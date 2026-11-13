# Sog'lig'im — Galaxy Fit3 / Samsung Health dashboard

`dashboard.html` — Samsung Health'dan eksport qilingan ma'lumotlar (ZIP yoki CSV) asosida
qadamlar, uyqu (bosqichlari bilan), dam olishdagi puls, SpO2, stress va mashg'ulotlar dashboardi.

- Fayllar faqat brauzerda o'qiladi, serverga yuborilmaydi. Kunlik ko'rsatkichlar `localStorage`da saqlanadi.
- Ma'lumot yuklanmaguncha namuna (demo) ma'lumot ko'rsatiladi.
- Tashqi bog'liqlik: ZIP o'qish uchun JSZip (cdnjs).

Bu 0-bosqich (MVP). Keyingi bosqichlar: Health Connect orqali avtomatik sinxronlovchi Android ilova,
backend va Telegram bot orqali kunlik xulosalar.
