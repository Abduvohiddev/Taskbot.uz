"""@uniccodebot: buyruqlar va fayl qabul qilish."""
import asyncio
import logging
import os
import tempfile
from typing import Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from uniccode import excel_out, generator, importer, parsers
from uniccode.config import UnicSettings
from uniccode.models import UCCode, UCCounter
from uniccode.sheets_sync import SheetSync

log = logging.getLogger("uniccode.bot")

HELP = (
    "<b>Unikal kod bot</b>\n\n"
    "<b>/kod 844088 5</b> — artikulga 5 ta kod. Oxiriga izoh yozsa bo'ladi: <code>/kod 844088 5 T535</code>\n"
    "<b>/oxirgi 844088</b> — artikulning oxirgi kodlari\n"
    "<b>/holat</b> — baza va Google Sheets holati\n\n"
    "<b>Excel fayl yuboring:</b>\n"
    "• 1C sklad hisoboti (Движения товаров) — qaysi qatorlar kerakligini so'rayman\n"
    "• Ro'yxat: <i>Артикул</i>, <i>Кол-во</i> ustunlari (ixtiyoriy: <i>Seria</i>, <i>Адрес</i>, "
    "<i>Наименование</i>, <i>Izoh</i>)\n\n"
    "Admin: <b>/import</b> — Google Sheets'dan yuklab olingan eski bazani (xlsx) SQL ga ko'chirish"
)


class St(StatesGroup):
    import_wait = State()
    stock_selector = State()
    stock_mode = State()
    list_confirm = State()


def kb(*buttons):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d)] for t, d in buttons])


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
        await state.clear()
        parts = (command.args or "").split(maxsplit=2)
        if len(parts) < 2 or not parts[1].isdigit():
            await m.answer("Masalan: <code>/kod 844088 5</code> yoki <code>/kod 844088 5 T535</code>")
            return
        art = generator.normalize_article(parts[0])
        if not generator.ARTICLE_RE.match(art):
            await m.answer("Artikul 6 xonali raqam bo'lishi kerak.")
            return
        note = parts[2] if len(parts) > 2 else None
        await run_generate(m, [generator.Item(article=art, qty=int(parts[1]), note=note)], "kod", note=note)

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
            if await state.get_state() == St.import_wait.state:
                await m.answer("Import boshlandi, katta baza bo'lsa 1-2 daqiqa ketadi…")
                rows, max_seq, stats = await asyncio.to_thread(importer.read_legacy, path, cfg.UNIC_TZ)
                async with sm() as session:
                    stats = await importer.import_rows(session, rows, max_seq, stats, m.from_user.id, name)
                await state.clear()
                txt = (f"✅ Import tugadi.\nO'qildi: {stats.rows_read}\nYangi yozildi: {stats.inserted}\n"
                       f"Faylda takror kodlar: {stats.duplicates_in_file}\nNostandart (saqlandi): {stats.irregular}\n"
                       f"O'qib bo'lmadi: {stats.invalid}\n"
                       f"Artikullar: {stats.articles}")
                if stats.invalid_samples:
                    txt += "\nBuzuq kod misollari: " + ", ".join(stats.invalid_samples[:5])
                await m.answer(txt)
                return
            rows = await asyncio.to_thread(parsers.read_rows, path)

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
        await m.answer("Faylni tushunmadim. 1C sklad hisoboti yoki <i>Артикул</i> va <i>Кол-во</i> ustunli ro'yxat yuboring.")

    @r.message(St.stock_selector, F.text)
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
