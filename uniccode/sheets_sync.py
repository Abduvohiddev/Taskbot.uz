"""
Kodlarni Google Sheet'ga real vaqtga yaqin yuklash.

Har GSHEET_SYNC_INTERVAL soniyada synced=False kodlar olinadi va jadvalning uchta varag'iga qo'shiladi:
GSHEET_WORKSHEET (hammasi), GSHEET_CHEXOL_TAB va GSHEET_POLIK_TAB (mahsulot turiga qarab), so'ng synced=True
qilinadi. Google ishlamay qolsa kodlar bazada kutib turadi va keyingi urinishda yuklanadi - bot ishlashda
davom etadi. rebuild() varaqlarni bazadagi barcha kodlar bilan qaytadan to'ldiradi (/jadval).
"""
import asyncio
import json
import logging
import re
from typing import Dict, List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from uniccode.config import UnicSettings
from uniccode.generator import to_local
from uniccode.models import UCCode, UCProduct

log = logging.getLogger("uniccode.sheets")

HEADER = ["Дата", "Артикул", "Уникальный код", "Уникальный код", "Izoh", "Адрес", "Наименование", "Seria", "Mashina",
          "Vid"]
CHEXOL, POLIK = "chexol", "polik"


def category(vid: Optional[str], name: Optional[str], cfg: UnicSettings) -> str:
    """Polik yoki chexol: 1C dagi vid bo'yicha, vid noma'lum bo'lsa nomidan. Qolgan hammasi chexol bo'liminiki."""
    if vid:
        return POLIK if re.search(cfg.UNIC_POLIK_VID_RE, vid, re.I) else CHEXOL
    return POLIK if name and re.search(cfg.UNIC_POLIK_NAME_RE, name, re.I) else CHEXOL


class SheetSync:
    def __init__(self, sessionmaker: async_sessionmaker, settings: UnicSettings):
        self.sm = sessionmaker
        self.s = settings
        self._sh = None
        self._ws: Dict[str, object] = {}
        self._lock = asyncio.Lock()
        self.last_error: Optional[str] = None

    @property
    def tabs(self) -> Dict[str, str]:
        """{'all'|'chexol'|'polik': varaq nomi}."""
        t = {"all": self.s.GSHEET_WORKSHEET}
        if self.s.GSHEET_CHEXOL_TAB and self.s.GSHEET_POLIK_TAB:
            t.update({CHEXOL: self.s.GSHEET_CHEXOL_TAB, POLIK: self.s.GSHEET_POLIK_TAB})
        return t

    def _spreadsheet(self):
        if self._sh is None:
            import gspread
            if self.s.GOOGLE_CREDENTIALS_JSON:
                gc = gspread.service_account_from_dict(json.loads(self.s.GOOGLE_CREDENTIALS_JSON))
            else:
                gc = gspread.service_account(filename=self.s.GOOGLE_CREDENTIALS_FILE)
            self._sh = gc.open_by_key(self.s.GSHEET_ID)
        return self._sh

    def _worksheet(self, title: str):
        if title in self._ws:
            return self._ws[title]
        import gspread
        sh = self._spreadsheet()
        try:
            ws = sh.worksheet(title)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title, rows=1000, cols=len(HEADER))
            ws.append_row(HEADER, value_input_option="RAW")
        if ws.col_count < len(HEADER):           # eski varaqqa keyin qo'shilgan ustunlar
            ws.add_cols(len(HEADER) - ws.col_count)
        if ws.row_values(1) != HEADER:
            ws.update(range_name="A1", values=[HEADER], value_input_option="RAW")
        self._ws[title] = ws
        return ws

    def _append(self, title: str, values: List[list]) -> None:
        self._worksheet(title).append_rows(values, value_input_option="RAW", insert_data_option="INSERT_ROWS")

    def _push(self, values: List[list], cats: List[str]) -> None:
        """Hammasi varag'iga va har bir qatorni o'z turidagi varaqqa."""
        tabs = self.tabs
        self._append(tabs["all"], values)
        for cat in (CHEXOL, POLIK):
            part = [v for v, c in zip(values, cats) if c == cat]
            if part and cat in tabs:
                self._append(tabs[cat], part)

    def _query(self):
        return (select(UCCode.id, UCCode.created_at, UCCode.article, UCCode.seq, UCCode.code, UCCode.note,
                       UCCode.address, UCCode.name, UCCode.series, UCCode.machine, UCProduct.vid,
                       UCProduct.name.label("pname"))
                .outerjoin(UCProduct, UCProduct.article == UCCode.article))

    def _rows(self, rows):
        values, cats = [], []
        for r in rows:
            name = r.name or r.pname or ""
            values.append([
                to_local(r.created_at, self.s.UNIC_TZ).strftime("%d/%m/%Y %H:%M:%S"), int(r.article), int(r.seq),
                r.code, r.note or "", r.address or "", name, r.series or "", r.machine or "", r.vid or "",
            ])
            cats.append(category(r.vid, name, self.s))
        return values, cats

    async def sync_once(self) -> int:
        async with self._lock:
            async with self.sm() as session:
                rows = (await session.execute(
                    self._query().where(UCCode.synced.is_(False)).order_by(UCCode.id).limit(self.s.GSHEET_BATCH)
                )).all()
                if not rows:
                    return 0
                values, cats = self._rows(rows)
                await asyncio.to_thread(self._push, values, cats)
                await session.execute(update(UCCode).where(UCCode.id.in_([r.id for r in rows])).values(synced=True))
                await session.commit()
                return len(rows)

    def _clear(self, title: str) -> None:
        ws = self._worksheet(title)
        ws.clear()
        ws.update(range_name="A1", values=[HEADER], value_input_option="RAW")

    async def rebuild(self, page: int = 20000, progress=None) -> Dict[str, int]:
        """Varaqlarni tozalab, bazadagi barcha kodlarni (sana bo'yicha) qaytadan yozadi."""
        counts = {"all": 0, CHEXOL: 0, POLIK: 0}
        async with self._lock:
            async with self.sm() as session:
                max_id = (await session.execute(select(func.max(UCCode.id)))).scalar_one() or 0
            for title in self.tabs.values():
                await asyncio.to_thread(self._clear, title)
            offset = 0
            while True:
                async with self.sm() as session:
                    rows = (await session.execute(
                        self._query().where(UCCode.id <= max_id).order_by(UCCode.created_at, UCCode.id)
                        .offset(offset).limit(page)
                    )).all()
                if not rows:
                    break
                values, cats = self._rows(rows)
                await asyncio.to_thread(self._push, values, cats)
                counts["all"] += len(values)
                for c in cats:
                    counts[c] += 1
                offset += len(rows)
                if progress:
                    await progress(counts["all"])
                await asyncio.sleep(1)  # Google kvotasi: daqiqasiga 60 ta yozish
            async with self.sm() as session:
                await session.execute(update(UCCode).where(UCCode.id <= max_id).values(synced=True))
                await session.commit()
        return counts

    async def pending(self) -> int:
        async with self.sm() as session:
            return (await session.execute(select(func.count()).select_from(UCCode).where(UCCode.synced.is_(False)))).scalar_one()

    async def run_forever(self) -> None:
        log.info("Google Sheets sinxronlash yoqildi: %s / %s", self.s.GSHEET_ID, ", ".join(self.tabs.values()))
        while True:
            try:
                n = await self.sync_once()
                self.last_error = None
                if n:
                    log.info("Google Sheets'ga %s ta kod yuklandi", n)
                    if n >= self.s.GSHEET_BATCH:
                        await asyncio.sleep(1.5)  # navbat katta: Google kvotasiga urilmasdan tez davom etamiz
                        continue
            except asyncio.CancelledError:
                raise
            except Exception as e:  # tarmoq/kvota xatolari: keyinroq qayta urinamiz
                self.last_error = f"{type(e).__name__}: {e}"
                self._sh, self._ws = None, {}
                log.warning("Google Sheets sinxronlash xatosi: %s", self.last_error)
            await asyncio.sleep(self.s.GSHEET_SYNC_INTERVAL)
