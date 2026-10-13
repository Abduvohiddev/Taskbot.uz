"""
AI yordamchi: xatolarni oddiy tilda tushuntiradi va kunlik hisobot yozadi.
Provayder: Google Gemini (GEMINI_API_KEY) yoki Claude (ANTHROPIC_API_KEY). Kalit bo'lmasa o'chiq -
bot va xabarnomalar AI'siz ishlayveradi.
"""
import json
import logging
import re
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


GEMINI_FALLBACK = "gemini-2.5-flash"
_SKIP = re.compile(r"preview|exp|lite|image|tts|live|audio|thinking|embedding|vision|learnlm|gemma", re.I)


def pick_gemini_model(names: List[str]) -> Optional[str]:
    """Ro'yxatdan eng yangi barqaror 'flash' modelini tanlaydi (masalan gemini-2.5-flash)."""
    best = None
    for full in names:
        n = full.split("/")[-1]
        m = re.fullmatch(r"gemini-(\d+(?:\.\d+)?)-flash(?:-\d+)?", n)
        if m and not _SKIP.search(n):
            key = (float(m.group(1)), -len(n))
            if best is None or key > best[0]:
                best = (key, n)
    return best[1] if best else None


class AI:
    def __init__(self, cfg: UnicSettings, client=None, provider: Optional[str] = None):
        """client - testlar uchun (tayyor Anthropic yoki Gemini mijozi)."""
        self.cfg = cfg
        self.provider = provider or cfg.ai_provider or ("claude" if client is not None else "")
        self.enabled = cfg.ai_enabled or client is not None
        self.client = client
        self.model = cfg.UNIC_AI_MODEL if self.provider == "claude" else cfg.GEMINI_MODEL
        if client is None and self.enabled:
            if self.provider == "gemini":
                from google import genai
                self.client = genai.Client(api_key=cfg.GEMINI_API_KEY)
            else:
                self.client = anthropic.AsyncAnthropic(api_key=cfg.ANTHROPIC_API_KEY, timeout=120.0)

    @property
    def label(self) -> str:
        return f"{self.provider} ({self.model or 'avtomatik'})" if self.enabled else "o'chiq"

    async def ask(self, prompt: str, effort: str = "low", max_tokens: int = 4000) -> Optional[str]:
        """Bitta so'rov. Xato yoki rad etilsa None (chaqiruvchi AI'siz davom etadi)."""
        if not self.enabled:
            return None
        if self.provider == "gemini":
            return await self._ask_gemini(prompt, max_tokens)
        return await self._ask_claude(prompt, effort, max_tokens)

    async def _gemini_model(self) -> str:
        if not self.model:
            try:
                names = [m.name async for m in await self.client.aio.models.list()
                         if "generateContent" in (m.supported_actions or [])]
                self.model = pick_gemini_model(names) or GEMINI_FALLBACK
            except Exception as e:
                log.warning("AI: Gemini modellar ro'yxati olinmadi (%s), %s ishlatiladi", e, GEMINI_FALLBACK)
                self.model = GEMINI_FALLBACK
            log.info("AI: Gemini modeli %s", self.model)
        return self.model

    async def _ask_gemini(self, prompt: str, max_tokens: int) -> Optional[str]:
        from google.genai import errors, types
        try:
            model = await self._gemini_model()
            resp = await self.client.aio.models.generate_content(
                model=model, contents=prompt,
                config=types.GenerateContentConfig(system_instruction=SYSTEM, max_output_tokens=max_tokens * 2),
            )
        except errors.ClientError as e:      # 400 kalit noto'g'ri, 403, 404 model, 429 chegara
            log.warning("AI (Gemini) xatosi %s: %s", e.code, str(e.message or e)[:300])
            return None
        except errors.ServerError as e:
            log.warning("AI (Gemini) server xatosi %s: %s", e.code, str(e.message or e)[:300])
            return None
        except Exception as e:               # tarmoq va h.k.
            log.warning("AI (Gemini): ulanib bo'lmadi: %s: %s", type(e).__name__, str(e)[:300])
            return None
        try:
            text = (resp.text or "").strip()
        except ValueError:                   # javob xavfsizlik filtri tomonidan to'silgan
            return None
        return text or None

    async def _ask_claude(self, prompt: str, effort: str, max_tokens: int) -> Optional[str]:
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
