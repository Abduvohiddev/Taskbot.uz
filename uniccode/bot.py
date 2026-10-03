"""@uniccodebot: buyruqlar va fayl qabul qilish."""
import asyncio
import logging
import os
import shutil
import tempfile
from typing import Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from uniccode import catalog, excel_out, generator, importer, onec, parsers
from uniccode.config import UnicSettings
from uniccode.models import UCCode, UCCounter
from uniccode.sheets_sync import SheetSync

log = logging.getLogger("uniccode.bot")

HELP = (
    "<b>Unikal kod bot</b>\n\n"
    "<b>/kod</b> — seriya: artikul, soni, konveyr, mashina so'raladi; ➕ Qo'shish, ✅ Tayyor → "
    "seriya Excel + RFID .xls. Oldindan yozsa ham bo'ladi: <code>/kod 814292 50</code> "
    "(keyin konveyr va mashina so'raladi)\n"
    "<b>844088 5</b> (slesh'siz) — tez: savolsiz 5 ta kod, Датабаза formatida. "
    "Izoh bilan: <code>844088 5 T535</code>\n"
    "<b>/oxirgi 844088</b> — artikulning oxirgi kodlari\n"
    "<b>/holat</b> — baza va Google Sheets holati\n\n"
    "<b>Excel fayl yuboring:</b>\n"
    "• 1C sklad hisoboti (Движения товаров) — qaysi qatorlar kerakligini so'rayman\n"
    "• Ro'yxat: <i>Артикул</i>, <i>Кол-во</i> ustunlari (ixtiyoriy: <i>Seria</i>, <i>Адрес</i>, "
    "<i>Наименование</i>, <i>Izoh</i>)\n\n"
    "Admin: <b>/import</b> — eski bazani (xlsx) SQL ga ko'chirish; <b>/katalog</b> — mahsulot nomlari faylini yuklash; "
    "<b>/katalog_1c</b> — katalogni 1C dan hozir yangilash\n"
    "<b>/bekor</b> — joriy amalni bekor qilish"
)


class St(StatesGroup):
    import_wait = State()
    catalog_wait = State()
    stock_selector = State()
    stock_mode = State()
    list_confirm = State()


def kb(*buttons):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d)] for t, d in buttons])


def kb_grid(buttons, per_row=3, extra=()):
    rows, row = [], []
    for t, d in buttons:
        row.append(InlineKeyboardButton(text=t, callback_data=d))
        if len(row) == per_row:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    for t, d in extra:
        rows.append([InlineKeyboardButton(text=t, callback_data=d)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


class Wz(StatesGroup):
    """/kod seriya so'rovi: artikul -> soni -> konveyr -> mashina -> savat."""
    article = State()
    qty = State()
    konveyr = State()
    machine = State()
    cart = State()


CANCEL_BTN = ("✖️ Bekor qilish", "cancel")


def build_router(sm: async_sessionmaker, cfg: UnicSettings, sync: Optional[SheetSync]) -> Router:
    r = Router()

    def allowed(uid: int) -> bool:
        ids = cfg.allowed_ids
        return not ids or uid in ids

    def is_admin(uid: int) -> bool:
        return not cfg.admin_ids or uid in cfg.admin_ids

    r.message.filter(lambda m: m.from_user and allowed(m.from_user.id))
    r.callback_query.filter(lambda c: c.from_user and allowed(c.from_user.id))

    async def run_generate(message: Message, items, source: str, filename=None, note=None, title=""):
        total = sum(i.qty for i in items)
        if total == 0:
            await message.answer("Kod yasash uchun soni 0 dan katta qator topilmadi.")
            return
        if total > cfg.UNIC_MAX_PER_REQUEST:
            await message.answer(f"Juda ko'p: {total} ta kod. Chegara {cfg.UNIC_MAX_PER_REQUEST}. "
                                 "Faylni bo'lib yuboring yoki UNIC_MAX_PER_REQUEST ni oshiring.")
            return
        u = message.chat
        try:
            async with sm() as session:
                res = await generator.generate(
                    session, items, type_code=cfg.UNIC_TYPE_CODE, start_seq=cfg.UNIC_START_SEQ, tz=cfg.UNIC_TZ,
                    source=source, user_id=u.id, username=getattr(u, "username", None), filename=filename,
                    batch_note=note,
                )
        except ValueError as e:
            await message.answer(f"❌ {e}")
            return
        data = await asyncio.to_thread(excel_out.build_excel, res, title)
        fname = f"Unik_kodlar_{res.created_at:%d-%m-%Y}_{res.batch_id}.xlsx"
        lines = [f"✅ {res.total} ta kod yasaldi ({len(res.items)} qator)."]
        if res.total <= 20:
            lines += [c for ir in res.items for c in ir.codes]
        else:
            for ir in res.items[:10]:
                lines.append(f"{ir.item.article} ×{len(ir.codes)}: {ir.codes[0]} … {ir.codes[-1]}")
            if len(res.items) > 10:
                lines.append(f"… yana {len(res.items) - 10} qator — Excel faylda.")
        if sync:
            lines.append("Google Sheets'ga bir necha soniyada yuklanadi.")
        await message.answer("\n".join(lines))
        await message.answer_document(BufferedInputFile(data, filename=fname))

    @r.message(Command("start", "help"))
    async def start(m: Message, state: FSMContext):
        await state.clear()
        await m.answer(HELP + f"\n\nSizning ID: <code>{m.from_user.id}</code>")

    @r.message(Command("kod"))
    async def kod(m: Message, command: CommandObject, state: FSMContext):
        """/kod -> seriya so'rovi. Argumentlar oldindan to'ldiradi va qolganini so'raydi:
        /kod 814292 -> soni so'raladi; /kod 814292 50 -> konveyr; /kod 814292 50 F-1795 -> mashina."""
        await state.clear()
        parts = (command.args or "").split()
        await state.update_data(cart=[], cur={}, opts=[])
        if not parts:
            await wz_ask_article(m, state)
            return
        art = generator.normalize_article(parts[0])
        if not generator.ARTICLE_RE.match(art):
            await m.answer("Artikul 6 xonali raqam bo'lishi kerak.")
            await wz_ask_article(m, state)
            return
        await wz_set_article(m, state, art, ask_next=len(parts) < 2)
        if len(parts) < 2:
            return
        if not parts[1].isdigit():
            await m.answer("Soni raqam bo'lishi kerak.")
            await wz_ask_qty(m, state)
            return
        if len(parts) < 3:
            await wz_set_qty(m, state, int(parts[1]))
            return
        data = await state.get_data()
        cur = data["cur"]
        cur["qty"] = int(parts[1])
        cur["konveyr"] = parts[2][:64]
        await state.update_data(cur=cur)
        if len(parts) >= 4:
            await state.set_state(Wz.machine)
            await wz_value(m, state, parts[3])
        else:
            await wz_ask_machine(m, state)

    @r.message(StateFilter(None), F.text.regexp(r"^\s*(x-)?\d{6}\s+\d+(\s+.*)?$"))
    async def kod_plain(m: Message, state: FSMContext):
        """'844088 5' yoki '844088 5 T535' — /kod siz ham ishlaydi."""
        parts = m.text.split(maxsplit=2)
        art = generator.normalize_article(parts[0])
        note = parts[2].strip() if len(parts) > 2 else None
        await run_generate(m, [generator.Item(article=art, qty=int(parts[1]), note=note)], "kod", note=note)

    # ------------------------------------------------------------------ /kod seriya so'rovi
    async def recent(column, limit=6):
        async with sm() as session:
            q = (select(column, func.max(UCCode.id).label("mx")).where(column.isnot(None), column != "")
                 .group_by(column).order_by(func.max(UCCode.id).desc()).limit(limit))
            return [r[0] for r in (await session.execute(q)).all()]

    def uniq(values):
        out = []
        for v in values:
            if v and v not in out:
                out.append(v)
        return out[:9]

    def cart_text(cart):
        lines = ["🧾 <b>Seriya</b>"]
        for i, c in enumerate(cart, 1):
            un = excel_out.umumiy_nomi(c["konveyr"], c["machine"])
            lines.append(f"{i}) <b>{c['article']}</b> × {c['qty']} — {un}\n    <i>{c.get('name') or 'nomi katalogda yo`q'}</i>")
        lines.append(f"\nJami: <b>{sum(c['qty'] for c in cart)}</b> ta kod")
        return "\n".join(lines)

    async def show_cart(target: Message, state: FSMContext):
        data = await state.get_data()
        await state.set_state(Wz.cart)
        btns = [("➕ Qo'shish", "wz:add"), ("✅ Tayyor", "wz:done")]
        extra = [("↩️ Oxirgisini o'chirish", "wz:undo"), CANCEL_BTN]
        await target.answer(cart_text(data["cart"]), reply_markup=kb_grid(btns, 2, extra))

    async def wz_ask_article(target: Message, state: FSMContext):
        data = await state.get_data()
        await state.set_state(Wz.article)
        n = len(data.get("cart", [])) + 1
        await target.answer(f"<b>{n}-qator.</b> 1/4. Artikulni yozing (6 xonali), masalan <code>814292</code>",
                            reply_markup=kb(CANCEL_BTN))

    async def wz_ask_qty(target: Message, state: FSMContext):
        await state.set_state(Wz.qty)
        btns = [(str(n), f"qty:{n}") for n in (10, 20, 30, 50, 100, 200)]
        await target.answer("2/4. Nechta kod kerak? Tugmani bosing yoki sonni yozing.",
                            reply_markup=kb_grid(btns, 3, [CANCEL_BTN]))

    async def wz_ask_konveyr(target: Message, state: FSMContext):
        data = await state.get_data()
        last = [c["konveyr"] for c in reversed(data.get("cart", []))]
        opts = uniq(last + await recent(UCCode.series))
        await state.update_data(opts=opts)
        await state.set_state(Wz.konveyr)
        await target.answer("3/4. Konveyr? Tanlang yoki yozing (masalan <code>F-1795</code>).",
                            reply_markup=kb_grid([(o, f"opt:{i}") for i, o in enumerate(opts)], 3, [CANCEL_BTN]))

    async def wz_ask_machine(target: Message, state: FSMContext):
        data = await state.get_data()
        last = [c["machine"] for c in reversed(data.get("cart", []))]
        opts = uniq([data["cur"].get("marka")] + last + await recent(UCCode.machine))
        await state.update_data(opts=opts)
        await state.set_state(Wz.machine)
        await target.answer("4/4. Mashinasi? Tanlang yoki yozing (masalan <code>COB</code>).",
                            reply_markup=kb_grid([(o, f"opt:{i}") for i, o in enumerate(opts)], 3, [CANCEL_BTN]))

    @r.message(Command("bekor"))
    async def bekor(m: Message, state: FSMContext):
        await state.clear()
        await m.answer("Bekor qilindi.")

    async def wz_set_article(m: Message, state: FSMContext, art: str, ask_next: bool = True):
        async with sm() as session:
            prods = await catalog.get_products(session, [art])
        p = prods.get(art)
        await state.update_data(cur={"article": art, "name": p.name if p else None, "marka": p.marka if p else None})
        await m.answer(f"<b>{art}</b> — {p.name}" if p else f"<b>{art}</b> — ⚠️ katalogda topilmadi, nomi bo'sh qoladi.")
        if ask_next:
            await wz_ask_qty(m, state)

    @r.message(Wz.article, F.text, ~F.text.startswith("/"))
    async def wz_article(m: Message, state: FSMContext):
        art = generator.normalize_article(m.text.strip())
        if not generator.ARTICLE_RE.match(art):
            await m.answer("Artikul 6 xonali raqam bo'lishi kerak. Qaytadan yozing.")
            return
        await wz_set_article(m, state, art)

    async def wz_set_qty(target: Message, state: FSMContext, qty: int):
        if qty <= 0 or qty > cfg.UNIC_MAX_PER_REQUEST:
            await target.answer(f"Soni 1 dan {cfg.UNIC_MAX_PER_REQUEST} gacha bo'lishi kerak.")
            return
        data = await state.get_data()
        cur = data["cur"]
        cur["qty"] = qty
        await state.update_data(cur=cur)
        await wz_ask_konveyr(target, state)

    @r.message(Wz.qty, F.text, ~F.text.startswith("/"))
    async def wz_qty_text(m: Message, state: FSMContext):
        t = m.text.strip().replace(" ", "")
        if not t.isdigit():
            await m.answer("Faqat son yozing, masalan <code>50</code>.")
            return
        await wz_set_qty(m, state, int(t))

    @r.callback_query(Wz.qty, F.data.startswith("qty:"))
    async def wz_qty_btn(c: CallbackQuery, state: FSMContext):
        await c.message.edit_reply_markup()
        await c.answer()
        await wz_set_qty(c.message, state, int(c.data.split(":")[1]))

    async def wz_value(target: Message, state: FSMContext, value: str):
        value = value.strip()[:64]
        if not value:
            return
        data = await state.get_data()
        cur = data["cur"]
        if await state.get_state() == Wz.konveyr.state:
            cur["konveyr"] = value
            await state.update_data(cur=cur)
            await wz_ask_machine(target, state)
        else:
            cur["machine"] = value
            cart = data.get("cart", []) + [cur]
            await state.update_data(cart=cart, cur={})
            await show_cart(target, state)

    @r.message(StateFilter(Wz.konveyr, Wz.machine), F.text, ~F.text.startswith("/"))
    async def wz_value_text(m: Message, state: FSMContext):
        await wz_value(m, state, m.text)

    @r.callback_query(StateFilter(Wz.konveyr, Wz.machine), F.data.startswith("opt:"))
    async def wz_value_btn(c: CallbackQuery, state: FSMContext):
        opts = (await state.get_data()).get("opts", [])
        i = int(c.data.split(":")[1])
        await c.message.edit_reply_markup()
        await c.answer()
        if i < len(opts):
            await wz_value(c.message, state, opts[i])

    @r.message(Wz.cart, F.text, ~F.text.startswith("/"))
    async def wz_cart_text(m: Message, state: FSMContext):
        await m.answer("Tugmalardan birini bosing: ➕ Qo'shish yoki ✅ Tayyor.")

    @r.callback_query(Wz.cart, F.data.startswith("wz:"))
    async def wz_cart_btn(c: CallbackQuery, state: FSMContext):
        await c.message.edit_reply_markup()
        await c.answer()
        data = await state.get_data()
        cart = data.get("cart", [])
        if c.data == "wz:add":
            await wz_ask_article(c.message, state)
        elif c.data == "wz:undo":
            cart = cart[:-1]
            await state.update_data(cart=cart)
            if cart:
                await show_cart(c.message, state)
            else:
                await wz_ask_article(c.message, state)
        elif c.data == "wz:done" and cart:
            await state.clear()
            items = [generator.Item(article=x["article"], qty=x["qty"], name=x.get("name"), series=x["konveyr"],
                                    machine=x["machine"], note=x["konveyr"]) for x in cart]
            await run_seria(c.message, items)

    async def run_seria(message: Message, items):
        total = sum(i.qty for i in items)
        if total > cfg.UNIC_MAX_PER_REQUEST:
            await message.answer(f"Juda ko'p: {total} ta kod. Chegara {cfg.UNIC_MAX_PER_REQUEST}.")
            return
        u = message.chat
        try:
            async with sm() as session:
                res = await generator.generate(
                    session, items, type_code=cfg.UNIC_TYPE_CODE, start_seq=cfg.UNIC_START_SEQ, tz=cfg.UNIC_TZ,
                    source="seriya", user_id=u.id, username=getattr(u, "username", None),
                )
        except ValueError as e:
            await message.answer(f"❌ {e}")
            return
        seria = await asyncio.to_thread(excel_out.build_seria, res, cfg.UNIC_SERIA_I)
        stamp = f"{res.created_at:%d-%m-%Y}_{res.batch_id}"
        lines = [f"✅ {res.total} ta kod yasaldi."]
        for ir in res.items:
            lines.append(f"{ir.item.article} ×{len(ir.codes)} ({excel_out.umumiy_nomi(ir.item.series, ir.item.machine)}): "
                         f"{ir.codes[0]} … {ir.codes[-1]}")
        nameless = sorted({ir.item.article for ir in res.items if not ir.item.name})
        if nameless:
            lines.append("\n⚠️ Katalogda yo'q, nomeklatura bo'sh qoldi: " + ", ".join(nameless) +
                         "\nKatalog faylini /katalog orqali yuboring.")
        await message.answer("\n".join(lines[:30]))
        await message.answer_document(BufferedInputFile(seria, filename=f"seria_{stamp}.xlsx"))
        try:
            rfid = await asyncio.to_thread(excel_out.build_rfid_xls, res)
            await message.answer_document(BufferedInputFile(rfid, filename=f"rfid_{stamp}.xls"))
        except ValueError as e:
            await message.answer(f"⚠️ RFID fayl yasalmadi: {e}")

    @r.message(Command("katalog_1c"))
    async def katalog_1c(m: Message, state: FSMContext):
        if not is_admin(m.from_user.id):
            await m.answer("Bu buyruq faqat admin uchun.")
            return
        if not cfg.onec_enabled:
            await m.answer("1C ulanmagan: serverdagi .env ga ONEC_BASE_URL, ONEC_USER, ONEC_PASSWORD yozilmagan.")
            return
        await m.answer("1C dan nomenklatura olinmoqda, 1-2 daqiqa…")
        try:
            n = await sync_catalog_from_1c(sm, cfg)
        except onec.OneCError as e:
            await m.answer(f"❌ {e}")
            return
        await m.answer(f"✅ Katalog 1C dan yangilandi: {n} ta artikul.")

    @r.message(Command("katalog"))
    async def katalog_cmd(m: Message, state: FSMContext):
        if not is_admin(m.from_user.id):
            await m.answer("Bu buyruq faqat admin uchun.")
            return
        await state.set_state(St.catalog_wait)
        await m.answer("Mahsulot katalogi faylini yuboring (xlsx/xls): <i>Артикул</i> va <i>Номенклатура</i> ustunlari. "
                       "Bor artikullarning nomi yangilanadi.")

    @r.message(Command("oxirgi"))
    async def oxirgi(m: Message, command: CommandObject):
        art = generator.normalize_article((command.args or "").strip())
        if not generator.ARTICLE_RE.match(art):
            await m.answer("Masalan: <code>/oxirgi 844088</code>")
            return
        async with sm() as session:
            last, rows = await generator.last_codes(session, art)
        if last is None:
            await m.answer(f"{art} bazada yo'q. Birinchi kod {cfg.UNIC_START_SEQ} dan boshlanadi.")
            return
        txt = [f"<b>{art}</b>: oxirgi band raqam <code>{last}</code>, keyingisi <code>{last + 1}</code>"]
        txt += [f"<code>{c}</code>  {generator.to_local(d, cfg.UNIC_TZ):%d.%m.%Y %H:%M}  {n or ''}" for c, d, n in rows]
        await m.answer("\n".join(txt))

    @r.message(Command("holat"))
    async def holat(m: Message):
        async with sm() as session:
            codes = (await session.execute(select(func.count()).select_from(UCCode))).scalar_one()
            arts = (await session.execute(select(func.count()).select_from(UCCounter))).scalar_one()
            pend = (await session.execute(select(func.count()).select_from(UCCode).where(UCCode.synced.is_(False)))).scalar_one()
        txt = [f"Bazada kodlar: <b>{codes}</b>", f"Artikullar: <b>{arts}</b>"]
        if sync:
            txt.append(f"Google Sheets'ga yuklanishi kutilmoqda: <b>{pend}</b>")
            if sync.last_error:
                txt.append(f"Oxirgi xato: <code>{sync.last_error[:300]}</code>")
        else:
            txt.append("Google Sheets sinxronlash o'chiq: GSHEET_ID yoki service account kaliti "
                       "(secrets/google.json) yo'q. Kalit qo'yilgach botni qayta ishga tushiring.")
        await m.answer("\n".join(txt))

    @r.message(Command("import"))
    async def imp(m: Message, state: FSMContext):
        if not is_admin(m.from_user.id):
            await m.answer("Bu buyruq faqat admin uchun.")
            return
        await state.set_state(St.import_wait)
        await m.answer("Google Sheets'dagi bazani <b>Файл → Скачать → Microsoft Excel (.xlsx)</b> qilib yuklab, "
                       "shu yerga yuboring. Bor kodlar takror yozilmaydi, hisoblagichlar eng katta raqamga ko'tariladi.")

    @r.message(F.document)
    async def document(m: Message, state: FSMContext, bot: Bot):
        name = m.document.file_name or "file.xlsx"
        if not name.lower().endswith((".xls", ".xlsx")):
            await m.answer("Faqat .xls yoki .xlsx fayl qabul qilaman.")
            return
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, name)
            await bot.download(m.document, destination=path)
            if await state.get_state() == St.catalog_wait.state:
                items = await asyncio.to_thread(catalog.parse_catalog, path)
                async with sm() as session:
                    n = await catalog.save_catalog(session, items)
                await state.clear()
                await m.answer(f"✅ Katalog yangilandi: {n} ta artikul." if n else
                               "Faylda artikul va nomli qator topilmadi.")
                return
            if await state.get_state() == St.import_wait.state:
                await m.answer("Import boshlandi, katta baza bo'lsa 1-2 daqiqa ketadi…")
                rows, max_seq, stats = await asyncio.to_thread(importer.read_legacy, path, cfg.UNIC_TZ)
                async with sm() as session:
                    stats = await importer.import_rows(session, rows, max_seq, stats, m.from_user.id, name)
                await state.clear()
                txt = (f"✅ Import tugadi.\nO'qildi: {stats.rows_read}\nYangi yozildi: {stats.inserted}\n"
                       f"Faylda takror kodlar: {stats.duplicates_in_file}\nNostandart (saqlandi): {stats.irregular}\n"
                       f"O'qib bo'lmadi: {stats.invalid}\n"
                       f"Artikullar: {stats.articles}\n"
                       f"'Уник код' varag'idagi saqlanmagan kodlar (band qilindi): {stats.pending_reserved}")
                if stats.invalid_samples:
                    txt += "\nBuzuq kod misollari: " + ", ".join(stats.invalid_samples[:5])
                await m.answer(txt)
                return
            rows = await asyncio.to_thread(parsers.read_rows, path)
            path_copy = None
            if not parsers.parse_stock_report(rows) and not (parsers.parse_list(rows) or parsers.ListFile([])).items:
                path_copy = os.path.join(tempfile.gettempdir(), f"uc_{m.document.file_unique_id}_{name}")
                shutil.copy(path, path_copy)

        report = parsers.parse_stock_report(rows)
        if report:
            summary = report.rows_summary()
            if not summary:
                await m.answer("Hisobotda qoldig'i bor qator topilmadi.")
                return
            nums = sorted([k for k in summary if k.isdigit()], key=int)
            other = sorted([k for k in summary if not k.isdigit()])
            lines = [f"📦 Sklad hisoboti. {report.period}".strip(), ""]
            lines += [f"{k}-qator: {summary[k]} dona" for k in nums]
            lines += [f"{k}: {summary[k]} dona" for k in other]
            lines += ["", "Qaysi qatorlar yoki joylar uchun kod kerak? Masalan: <code>9,1</code>, "
                          "<code>TM_6D3, S_TM-Transit</code> yoki <code>hammasi</code>"]
            await state.set_state(St.stock_selector)
            await state.update_data(stock=[(l.article, l.name, l.address, l.qty) for l in report.lines],
                                    filename=name, period=report.period)
            await m.answer("\n".join(lines))
            return

        lst = parsers.parse_list(rows)
        if lst and lst.items:
            total = sum(i.qty for i in lst.items)
            series = sorted({i.series for i in lst.items if i.series})
            txt = [f"📄 Ro'yxat: {len(lst.items)} qator, jami <b>{total}</b> ta kod."]
            if series:
                txt.append("Seriyalar: " + ", ".join(series[:15]) + (" …" if len(series) > 15 else ""))
            if lst.errors:
                txt.append(f"⚠️ O'tkazib yuborildi: {len(lst.errors)} qator")
                txt += lst.errors[:8]
            await state.set_state(St.list_confirm)
            await state.update_data(items=[(i.article, i.qty, i.address, i.name, i.series, i.note) for i in lst.items],
                                    filename=name)
            await m.answer("\n".join(txt), reply_markup=kb(("✅ Kod yasash", "list:go"), ("✖️ Bekor qilish", "cancel")))
            return
        # Soni ustuni yo'q, lekin Артикул + Номенклатура bor -> mahsulot katalogi (admin uchun)
        items = {}
        if path_copy:
            try:
                items = await asyncio.to_thread(catalog.parse_catalog, path_copy)
            finally:
                os.remove(path_copy)
        if items and is_admin(m.from_user.id):
            async with sm() as session:
                n = await catalog.save_catalog(session, items)
            await m.answer(f"📚 Bu mahsulot katalogi ekan. ✅ Katalog yangilandi: {n} ta artikul.")
            return
        await m.answer("Faylni tushunmadim. 1C sklad hisoboti, <i>Артикул</i> va <i>Кол-во</i> ustunli ro'yxat "
                       "yoki <i>Артикул</i> va <i>Номенклатура</i> ustunli katalog yuboring.")

    @r.message(St.stock_selector, F.text, ~F.text.startswith("/"))
    async def stock_selector(m: Message, state: FSMContext):
        data = await state.get_data()
        report = parsers.StockReport(lines=[parsers.StockLine(*t) for t in data["stock"]])
        chosen_all, _ = parsers.select_lines(report, m.text, only_chexol=False)
        chosen_chx, _ = parsers.select_lines(report, m.text, only_chexol=True)
        if not chosen_all:
            await m.answer("Bunday qator/joy topilmadi yoki qoldig'i yo'q. Qaytadan yozing, masalan <code>9,1</code>.")
            return
        await state.update_data(selector=m.text)
        await state.set_state(St.stock_mode)
        await m.answer(
            f"Tanlandi: <b>{m.text}</b>\nHamma tovar: {sum(l.qty for l in chosen_all)} dona ({len(chosen_all)} qator)\n"
            f"Faqat o'rindiq chexoli: {sum(l.qty for l in chosen_chx)} dona ({len(chosen_chx)} qator)",
            reply_markup=kb((f"Hammasiga ({sum(l.qty for l in chosen_all)})", "stock:all"),
                            (f"Faqat chexol ({sum(l.qty for l in chosen_chx)})", "stock:chx"),
                            ("✖️ Bekor qilish", "cancel")),
        )

    @r.callback_query(St.stock_mode, F.data.startswith("stock:"))
    async def stock_go(c: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        await state.clear()
        await c.message.edit_reply_markup()
        report = parsers.StockReport(lines=[parsers.StockLine(*t) for t in data["stock"]])
        only = c.data == "stock:chx"
        chosen, skipped = parsers.select_lines(report, data["selector"], only_chexol=only)
        title = (f"Manba: {data.get('filename')} {data.get('period', '')}\nTanlov: {data['selector']}"
                 f" ({'faqat chexol' if only else 'hamma tovar'})\nKod soni = Конечный остаток.")
        if skipped:
            title += "\nO'tkazib yuborildi (qoldig'i 0/manfiy yoki artikul noto'g'ri): " + ", ".join(f"{l.address} {l.article}" for l in skipped)
        await run_generate(c.message, parsers.stock_items(chosen), "sklad", filename=data.get("filename"),
                           note=data["selector"], title=title)
        await c.answer()

    @r.callback_query(St.list_confirm, F.data == "list:go")
    async def list_go(c: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        await state.clear()
        await c.message.edit_reply_markup()
        items = [generator.Item(article=a, qty=q, address=ad, name=n, series=s, note=nt)
                 for a, q, ad, n, s, nt in data["items"]]
        await run_generate(c.message, items, "royxat", filename=data.get("filename"),
                           title=f"Manba: {data.get('filename')}")
        await c.answer()

    @r.callback_query(F.data == "cancel")
    async def cancel(c: CallbackQuery, state: FSMContext):
        await state.clear()
        await c.message.edit_reply_markup()
        await c.answer("Bekor qilindi")

    return r


async def sync_catalog_from_1c(sm: async_sessionmaker, cfg: UnicSettings) -> int:
    items = await onec.fetch_catalog(cfg.ONEC_BASE_URL, cfg.ONEC_USER, cfg.ONEC_PASSWORD)
    if not items:
        raise onec.OneCError("1C dan bitta ham artikul kelmadi - katalog o'zgartirilmadi.")
    async with sm() as session:
        return await catalog.save_catalog(session, items)


async def onec_sync_forever(sm: async_sessionmaker, cfg: UnicSettings) -> None:
    """Ishga tushgandan 1 daqiqa o'tib, keyin har ONEC_SYNC_INTERVAL_HOURS soatda katalogni 1C dan yangilaydi."""
    await asyncio.sleep(60)
    while True:
        try:
            n = await sync_catalog_from_1c(sm, cfg)
            log.info("Katalog 1C dan yangilandi: %s ta artikul", n)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("1C katalog sinxronlash xatosi: %s", e)
        await asyncio.sleep(max(cfg.ONEC_SYNC_INTERVAL_HOURS, 0.25) * 3600)


def build_fallback_router(cfg: UnicSettings) -> Router:
    """Tushunilmagan xabarlar. Ruxsatsiz foydalanuvchiga ID sini ko'rsatadi (admin qo'shib qo'yishi uchun)."""
    r = Router()

    @r.message()
    async def fallback(m: Message):
        if m.chat.type != "private" or not m.from_user:
            return
        ids = cfg.allowed_ids
        if ids and m.from_user.id not in ids:
            await m.answer(f"Sizga ruxsat berilmagan. Adminga ID'ingizni yuboring: <code>{m.from_user.id}</code>")
        else:
            await m.answer("Tushunmadim. Buyruqlar ro'yxati: /help")

    return r


def build_dispatcher(sm, cfg, sync) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(build_router(sm, cfg, sync))
    dp.include_router(build_fallback_router(cfg))

    @dp.errors()
    async def on_error(event):
        log.exception("Kutilmagan xato", exc_info=event.exception)
        upd = event.update
        msg = upd.message or (upd.callback_query.message if upd.callback_query else None)
        if msg:
            try:
                await msg.answer("❌ Xatolik yuz berdi, qaytadan urinib ko'ring. Takrorlansa adminga ayting.")
            except Exception:
                pass
        return True

    return dp
