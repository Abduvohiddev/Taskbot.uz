"""
Telegram xabarnomalari:
- yangi xato/ogohlantirishlar - superadminlarga (AI yoqilgan bo'lsa tushuntirish bilan), 5 daqiqada ko'pi bilan bir marta;
- kunlik hisobot UNIC_REPORT_HOUR da: superadminlarga hammasi bo'yicha, bo'lim adminlariga o'z bo'limi bo'yicha.
Hisobotlar ham uc_events ga (source='hisobot') yoziladi va panelda ko'rinadi.
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from uniccode import stats
from uniccode.access import ADMIN, DEPT_NAMES, Access
from uniccode.ai import AI
from uniccode.config import UnicSettings
from uniccode.models import UCEvent

log = logging.getLogger("uniccode.notify")
TG_LIMIT = 3900


class Notifier:
    def __init__(self, sm: async_sessionmaker, cfg: UnicSettings, access: Access, ai: AI, send):
        """send(chat_id, text) - Telegram'ga matn yuboradi (testlarda almashtiriladi)."""
        self.sm, self.cfg, self.access, self.ai, self.send = sm, cfg, access, ai, send
        self._last_alert: Optional[datetime] = None

    async def _broadcast(self, ids, text: str) -> None:
        for uid in ids:
            for i in range(0, len(text), TG_LIMIT):
                try:
                    await self.send(uid, text[i:i + TG_LIMIT])
                except Exception as e:  # foydalanuvchi botni bloklagan va h.k.
                    log.info("Xabar yuborilmadi %s: %s", uid, e)

    async def alert_once(self) -> int:
        """Yuborilmagan xato/ogohlantirishlarni bitta xabar qilib superadminlarga yuboradi."""
        now = datetime.now(timezone.utc)
        if self._last_alert and now - self._last_alert < timedelta(minutes=5):
            return 0
        async with self.sm() as s:
            evs = (await s.execute(
                select(UCEvent).where(UCEvent.notified.is_(False), UCEvent.level.in_(("error", "warning")))
                .order_by(UCEvent.id).limit(30))).scalars().all()
            if not evs:
                return 0
            items = [{"id": e.id, "daraja": e.level, "manba": e.source, "xabar": e.message, "soni": e.count,
                      "vaqt": e.created_at, "tafsilot": (e.details or "")[-1500:]} for e in evs]
            explain = [i for i in items if i["manba"] != "ai"]
            ai_text = await self.ai.explain_errors(explain) if explain else None
            await s.execute(update(UCEvent).where(UCEvent.id.in_([e.id for e in evs]))
                            .values(notified=True, **({"ai_text": ai_text} if ai_text else {})))
            await s.commit()
        n_err = sum(1 for i in items if i["daraja"] == "error")
        head = f"⚠️ Botda {len(items)} ta yangi muammo ({n_err} ta xato)."
        lines = [f"• [{i['manba']}] {i['xabar'][:200]}" + (f" (×{i['soni']})" if i["soni"] > 1 else "")
                 for i in items[:10]]
        body = ("\n\n🤖 AI tahlili:\n" + ai_text) if ai_text else ""
        link = f"\n\nBatafsil: {self.cfg.PANEL_URL}/errors" if self.cfg.PANEL_URL else ""
        await self._broadcast(sorted(self.cfg.admin_ids), head + "\n" + "\n".join(lines) + body + link)
        self._last_alert = now
        return len(items)

    def _recipients(self) -> List[tuple]:
        """[(chat_id, bo'lim yoki None)] - superadminlar hammasini, bo'lim adminlari o'z bo'limini oladi."""
        out = [(uid, None) for uid in sorted(self.cfg.admin_ids)]
        for u in self.access._users.values():
            if u.active and u.role == ADMIN and u.dept and u.tg_id not in self.cfg.admin_ids:
                out.append((u.tg_id, u.dept))
        return out

    async def daily_report(self) -> int:
        texts = {}
        for uid, dept in self._recipients():
            if dept not in texts:
                async with self.sm() as s:
                    data = await stats.dashboard(s, self.cfg.UNIC_TZ, dept, days=30)
                data.pop("kunlik", None)
                scope = DEPT_NAMES.get(dept, dept)
                ai_text = await self.ai.daily_report(data, f"bo'lim: {scope}")
                t = data["jami"]
                plain = (f"Bugun: {t['bugun']} ta kod, 7 kunda: {t['7_kun']}, 30 kunda: {t['30_kun']}. "
                         f"Xatolar (24 soat): {data['xatolar_24_soat']}. Sheets'ga kutilmoqda: {data['sheets_kutilmoqda']}.")
                texts[dept] = f"📊 Kunlik hisobot — {scope} ({data['sana']})\n\n" + (ai_text or plain)
                async with self.sm() as s:
                    s.add(UCEvent(level="info", source="hisobot", message=f"Kunlik hisobot: {scope}",
                                  details=json.dumps(data, ensure_ascii=False, default=str)[:8000],
                                  ai_text=texts[dept], notified=True))
                    await s.commit()
            await self._broadcast([uid], texts[dept])
        return len(texts)

    async def _report_due(self) -> bool:
        if self.cfg.UNIC_REPORT_HOUR < 0:
            return False
        now = datetime.now(ZoneInfo(self.cfg.UNIC_TZ))
        if now.hour < self.cfg.UNIC_REPORT_HOUR:
            return False
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        async with self.sm() as s:
            q = select(UCEvent.id).where(UCEvent.source == "hisobot")
            if s.bind.dialect.name == "postgresql":
                q = q.where(UCEvent.created_at >= start)
            else:
                q = q.where(UCEvent.created_at >= start.astimezone(timezone.utc).replace(tzinfo=None))
            return (await s.execute(q.limit(1))).first() is None

    async def run_forever(self) -> None:
        await asyncio.sleep(30)
        while True:
            try:
                await self.alert_once()
                if await self._report_due():
                    await self.daily_report()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Notifier xatosi")
            await asyncio.sleep(60)
