"""
Yangi kodlarni alohida Google Sheet'ga real vaqtga yaqin yuklash.

Har GSHEET_SYNC_INTERVAL soniyada synced=False kodlar olinadi, bitta append_rows so'rovi bilan
jadval oxiriga qo'shiladi va synced=True qilinadi. Google ishlamay qolsa kodlar bazada kutib turadi
va keyingi urinishda yuklanadi - bot ishlashda davom etadi.
"""
import asyncio
import json
import logging
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from uniccode.config import UnicSettings
from uniccode.generator import to_local
from uniccode.models import UCCode

log = logging.getLogger("uniccode.sheets")

HEADER = ["Дата", "Артикул", "Уникальный код", "Уникальный код", "Izoh", "Адрес", "Наименование", "Seria"]


class SheetSync:
    def __init__(self, sessionmaker: async_sessionmaker, settings: UnicSettings):
        self.sm = sessionmaker
        self.s = settings
        self._ws = None
        self.last_error: Optional[str] = None

    def _worksheet(self):
        if self._ws is not None:
            return self._ws
        import gspread
        if self.s.GOOGLE_CREDENTIALS_JSON:
            gc = gspread.service_account_from_dict(json.loads(self.s.GOOGLE_CREDENTIALS_JSON))
        else:
            gc = gspread.service_account(filename=self.s.GOOGLE_CREDENTIALS_FILE)
        sh = gc.open_by_key(self.s.GSHEET_ID)
        try:
            ws = sh.worksheet(self.s.GSHEET_WORKSHEET)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(self.s.GSHEET_WORKSHEET, rows=1000, cols=len(HEADER))
            ws.append_row(HEADER, value_input_option="RAW")
        self._ws = ws
        return ws

    def _append(self, values: List[list]) -> None:
        self._worksheet().append_rows(values, value_input_option="RAW", insert_data_option="INSERT_ROWS")

    async def sync_once(self) -> int:
        async with self.sm() as session:
            rows = (await session.execute(
                select(UCCode).where(UCCode.synced.is_(False)).order_by(UCCode.id).limit(self.s.GSHEET_BATCH)
            )).scalars().all()
            if not rows:
                return 0
            values = [[
                to_local(r.created_at, self.s.UNIC_TZ).strftime("%d/%m/%Y %H:%M:%S"), int(r.article), int(r.seq), r.code,
                r.note or "", r.address or "", r.name or "", r.series or "",
            ] for r in rows]
            await asyncio.to_thread(self._append, values)
            await session.execute(update(UCCode).where(UCCode.id.in_([r.id for r in rows])).values(synced=True))
            await session.commit()
            return len(rows)

    async def pending(self) -> int:
        from sqlalchemy import func
        async with self.sm() as session:
            return (await session.execute(select(func.count()).select_from(UCCode).where(UCCode.synced.is_(False)))).scalar_one()

    async def run_forever(self) -> None:
        log.info("Google Sheets sinxronlash yoqildi: %s / %s", self.s.GSHEET_ID, self.s.GSHEET_WORKSHEET)
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
                self._ws = None
                log.warning("Google Sheets sinxronlash xatosi: %s", self.last_error)
            await asyncio.sleep(self.s.GSHEET_SYNC_INTERVAL)
