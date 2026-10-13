"""
AI yordamchi (Claude): xatolarni oddiy tilda tushuntiradi va kunlik hisobot yozadi.
ANTHROPIC_API_KEY bo'lmasa o'chiq - bot va xabarnomalar AI'siz ishlayveradi.
"""
import json
import logging
from typing import List, Optional

import anthropic

from uniccode.config import UnicSettings

log = logging.getLogger("uniccode.ai")

SYSTEM = (
    "Sen @uniccodebot yordamchisisan. Bot avtomobil chexollari va poliklari ishlab chiqaradigan korxonaning "
    "skladida mahsulotlarga unikal kod (RFID/EPC uchun) yasaydi. Kod formati: 6 xonali artikul + 'CA' + "
    "sana (KKOO) + 8 xonali tartib raqam. Bot PostgreSQL bazasi, Google Sheets (Hammasi/Chexol/Polik "
    "varaqlari), 1C OData (nomenklatura katalogi) va Telegram bilan ishlaydi. Ikki bo'lim bor: chexol va polik.\n"
    "Javobni o'zbek tilida (lotin), qisqa va aniq yoz: rahbar va sklad adminlari o'qiydi, dasturchi emas. "
    "Markdown, jadval va HTML ishlatma - oddiy matn va '•' bilan ro'yxat. Faqat berilgan ma'lumotga tayan, "
    "taxmin qilsang 'ehtimol' deb ayt."
)


class AI:
    def __init__(self, cfg: UnicSettings, client: Optional[anthropic.AsyncAnthropic] = None):
        self.cfg = cfg
        self.enabled = cfg.ai_enabled or client is not None
        self.client = client or (anthropic.AsyncAnthropic(api_key=cfg.ANTHROPIC_API_KEY, timeout=120.0)
                                 if cfg.ai_enabled else None)

    async def ask(self, prompt: str, effort: str = "low", max_tokens: int = 4000) -> Optional[str]:
        """Bitta so'rov. Xato yoki rad etilsa None (chaqiruvchi AI'siz davom etadi)."""
        if not self.enabled:
            return None
        try:
            resp = await self.client.beta.messages.create(
                model=self.cfg.UNIC_AI_MODEL,
                max_tokens=max_tokens,
                system=SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": effort},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",   # xavfsizlik filtri rad etsa, server boshqa modelda qayta urinadi
            )
        except anthropic.AuthenticationError:
            log.warning("AI: ANTHROPIC_API_KEY noto'g'ri yoki bekor qilingan")
            return None
        except anthropic.RateLimitError:
            log.warning("AI: so'rovlar chegarasi (429) - keyinroq")
            return None
        except anthropic.APIStatusError as e:
            log.warning("AI xatosi %s: %s", e.status_code, str(e.message)[:300])
            return None
        except anthropic.APIConnectionError as e:
            log.warning("AI: ulanib bo'lmadi: %s", e)
            return None
        if resp.stop_reason == "refusal":
            return None
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        return text or None

    async def explain_errors(self, events: List[dict]) -> Optional[str]:
        prompt = (
            "Botda quyidagi xatolar/ogohlantirishlar qayd etildi (JSON). Har biri uchun: nima bo'ldi, ehtimoliy "
            "sabab va admin nima qilishi kerak - 2-4 qatorda. Bir xil sababli xatolarni birlashtir. Agar xavfli "
            "bo'lmasa (vaqtinchalik tarmoq uzilishi va h.k.) shuni ayt.\n\n"
            + json.dumps(events, ensure_ascii=False, default=str)[:30000]
        )
        return await self.ask(prompt, effort="low")

    async def daily_report(self, stats: dict, scope: str) -> Optional[str]:
        prompt = (
            f"Bugungi kunlik hisobotni yoz ({scope}). Quyida bot statistikasi (JSON): bugun, 7 va 30 kunda "
            "yasalgan kodlar, bo'limlar, eng faol foydalanuvchilar va artikullar, xatolar, Google Sheets holati. "
            "Tuzilishi: 1) bugungi asosiy raqamlar, 2) odatdagidan farq qilgan narsalar (keskin o'sish/tushish, "
            "bitta foydalanuvchi juda ko'p kod yasagani, vidi aniqlanmagan mahsulotlar, xatolar), "
            "3) e'tibor berish kerak bo'lgan 1-3 ta tavsiya. 15 qatordan oshmasin.\n\n"
            + json.dumps(stats, ensure_ascii=False, default=str)[:30000]
        )
        return await self.ask(prompt, effort="medium")
