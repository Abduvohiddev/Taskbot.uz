"""
Ish orasida inglizcha hazil: kod yasalgandan keyin bot shu ishga oid qisqa hazilni ovozli xabar qilib yuboradi
(matni va o'zbekcha tarjimasi bilan - ingliz tilini o'rganishga ham foydali).

- Matn: AI yoqilgan bo'lsa yangi hazil yoziladi, aks holda tayyor ro'yxatdan olinadi.
- Ovoz: gTTS (mp3, Telegram voice), u ishlamasa Gemini TTS (wav). Ikkalasi ham ishlamasa faqat matn yuboriladi.
- Har bir foydalanuvchiga UNIC_JOKE_COOLDOWN_MIN daqiqada ko'pi bilan bitta - ishga xalaqit bermasligi uchun.
UNIC_JOKES=false - butunlay o'chiq.
"""
import asyncio
import io
import logging
import random
import re
import time
import wave
from typing import Dict, Optional, Tuple

from aiogram.types import BufferedInputFile, Message

from uniccode.ai import AI
from uniccode.config import UnicSettings

log = logging.getLogger("uniccode.jokes")

JOKES = [
    ("Why did the barcode go to therapy? It had too many unresolved lines.",
     "Shtrix-kod nega psixologga bordi? Unda hal qilinmagan chiziqlar juda ko'p edi."),
    ("I asked the warehouse manager for a unique code. He said: sorry, that one is already taken.",
     "Sklad mudiridan unikal kod so'radim. U: kechirasiz, bu kod allaqachon band, dedi."),
    ("Our RFID tags are so smart, they know where the seat covers are before the seat covers do.",
     "Bizning RFID teglarimiz shunchalik aqlliki, chexol qayerdaligini chexolning o'zidan oldin biladi."),
    ("Why don't warehouse workers play hide and seek? Because every box has a tracking code.",
     "Skladchilar nega bekinmachoq o'ynamaydi? Chunki har bir qutida kuzatuv kodi bor."),
    ("A returned car cover walked into the warehouse. The scanner said: welcome back, number 10000001!",
     "Qaytarilgan chexol skladga kirdi. Skaner: xush kelibsan, 10000001-raqam! dedi."),
    ("My code is so unique, even the database asked for its autograph.",
     "Kodim shunchalik unikalki, hatto baza ham undan avtograf so'radi."),
    ("Why was the floor mat so calm? Because it was always well grounded.",
     "Polik nega doim xotirjam? Chunki u doim yerga mustahkam bosib turadi."),
    ("The spreadsheet and the database got married. Now they never lose a single row.",
     "Jadval bilan baza turmush qurdi. Endi ular bitta qatorni ham yo'qotishmaydi."),
]

TOPICS = {
    "kod": "generating unique product codes in a car accessories warehouse",
    "seriya": "printing RFID labels for car seat covers",
    "sklad": "counting stock in warehouse cells",
    "royxat": "making unique codes for returned and moved goods",
    "import": "importing a huge database of product codes",
}


def parse(text: str) -> Optional[Tuple[str, str]]:
    """'EN: ...\\nUZ: ...' formatidagi javobdan (inglizcha, o'zbekcha)."""
    en = re.search(r"EN:\s*(.+?)(?:\n|$)", text or "", re.S)
    uz = re.search(r"UZ:\s*(.+?)(?:\n|$)", text or "", re.S)
    if not en or not uz:
        return None
    en_t, uz_t = en.group(1).strip().strip('"'), uz.group(1).strip().strip('"')
    if not (5 < len(en_t) < 300 and uz_t):
        return None
    return en_t, uz_t


class Joker:
    def __init__(self, cfg: UnicSettings, ai: Optional[AI] = None, tts=None):
        self.cfg, self.ai = cfg, ai
        self._last: Dict[int, float] = {}
        self._tts = tts  # testlar uchun: async (text) -> (bytes, filename, is_voice) | None

    def due(self, uid: int) -> bool:
        if not self.cfg.UNIC_JOKES:
            return False
        now = time.time()
        if now - self._last.get(uid, 0) < self.cfg.UNIC_JOKE_COOLDOWN_MIN * 60:
            return False
        self._last[uid] = now
        return True

    async def text(self, source: str) -> Tuple[str, str]:
        topic = TOPICS.get(source, TOPICS["kod"])
        if self.ai and self.ai.enabled:
            got = parse(await self.ai.ask(
                f"Write ONE short, clean, work-friendly English joke (max 2 short sentences, easy B1 English) about "
                f"{topic}. Reply in exactly two lines:\nEN: <the joke>\nUZ: <its Uzbek (Latin) translation>",
                effort="low", max_tokens=400) or "")
            if got:
                return got
        return random.choice(JOKES)

    async def speak(self, text: str):
        if self._tts:
            return await self._tts(text)
        try:
            return await asyncio.to_thread(_gtts, text), "joke.mp3", True
        except Exception as e:
            log.info("gTTS ishlamadi: %s", e)
        if self.ai and self.ai.enabled and self.ai.provider == "gemini":
            try:
                return await _gemini_tts(self.ai, text), "joke.wav", False
            except Exception as e:
                log.info("Gemini TTS ishlamadi: %s", e)
        return None

    async def send(self, message: Message, uid: int, source: str) -> bool:
        if not self.due(uid):
            return False
        try:
            en, uz = await self.text(source)
            caption = f"😄 {en}\n\n🇺🇿 {uz}"
            audio = await self.speak(en)
            if audio:
                data, fname, is_voice = audio
                f = BufferedInputFile(data, filename=fname)
                if is_voice:
                    await message.answer_voice(f, caption=caption, parse_mode=None)
                else:
                    await message.answer_audio(f, caption=caption, title="English joke", parse_mode=None)
            else:
                await message.answer(caption, parse_mode=None)
            return True
        except Exception as e:  # hazil hech qachon asosiy ishni buzmasin
            log.info("Hazil yuborilmadi: %s", e)
            return False

    def after(self, message: Message, uid: int, source: str) -> None:
        """Asosiy javobni kutdirmaslik uchun fonda yuboradi."""
        if self.cfg.UNIC_JOKES:
            asyncio.create_task(self.send(message, uid, source))


def _gtts(text: str) -> bytes:
    from gtts import gTTS
    buf = io.BytesIO()
    gTTS(text, lang="en", tld="com").write_to_fp(buf)
    return buf.getvalue()


async def _gemini_tts(ai: AI, text: str) -> bytes:
    from google.genai import types
    resp = await ai.client.aio.models.generate_content(
        model=ai.cfg.GEMINI_TTS_MODEL,
        contents=f"Say cheerfully: {text}",
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck"))),
        ),
    )
    pcm = resp.candidates[0].content.parts[0].inline_data.data
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:     # Gemini: 24 kHz, 16-bit, mono PCM
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)
    return buf.getvalue()
