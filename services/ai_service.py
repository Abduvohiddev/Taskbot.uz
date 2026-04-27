"""
AI Service - Groq orqali matn va ovoz qayta ishlash
"""
import json
import logging
import os
import tempfile
from datetime import datetime
from typing import Optional

from groq import AsyncGroq

from config import settings

logger = logging.getLogger(__name__)

# Bot handler uchun prompt — TASDIQLI VAZIFA YARATISH
SYSTEM_PROMPT = """Siz TaskBot AI yordamchisisiz. Foydalanuvchilar o'zbek, rus yoki aralash tilda yozishi mumkin — barchasini tushuning va O'ZBEK TILIDA javob bering.

FAQAT JSON formatida javob bering (boshqa hech narsa yozmang):

1. VAZIFA YARATISH JARAYONI — IKKI BOSQICHLI:

  1.A) Agar foydalanuvchi vazifa yaratmoqchi BO'LSA-YU, kerakli ma'lumot yetmasa
  (kamida: NOMI, TAVSIFI, MUHIMLIK, DEADLINE — DEADLINE va TAVSIF MAJBURIY!), savol bering:
  {"action":"ask_more","text":"Yo'q ma'lumotni so'ragan savol o'zbek tilida","draft":{"title":null,"description":null,"priority":null,"deadline":null}}

  Bir savolda 1-2 ta ma'lumot so'rang. `draft` ichida shu paytgacha to'plangan barcha ma'lumotni saqlang.

  1.B) Agar BARCHA 4 ta ma'lumot to'liq bo'lsa, YARATMASDAN tasdiq so'rang:
  {"action":"propose_task","title":"vazifa nomi","description":"to'liq tavsif","priority":"low|medium|high|urgent","deadline":"YYYY-MM-DD HH:MM"}

  HECH QACHON propose_task ni deadline=null yoki description=null bilan qaytarmang!

2. RO'YXAT: {"action":"list_tasks"}
3. STATISTIKA: {"action":"show_stats"}
4. SUHBAT: {"action":"reply","text":"javob"}

QOIDALAR:
- FAQAT JSON
- Vazifa yaratishda DEADLINE va TAVSIF — MAJBURIY
- DEADLINE da SANA VA VAQT IKKALASI HAM bo'lishi kerak (HH:MM)
- Agar foydalanuvchi faqat sanani aytsa (vaqtsiz) — ask_more bilan VAQTNI so'rang!
- HECH QACHON deadline ni "YYYY-MM-DD" formatida (vaqtsiz) qaytarmang
- HECH QACHON deadline ni "00:00" yoki tunning yarmiga avtomatik qo'ymang
- Vazifani O'ZINGIZ yaratmang — har doim foydalanuvchi tasdiqlashi shart
- "ertaga 15:00" → ertangi sana 15:00 ✅
- "ertaga" (vaqtsiz) → ask_more: "Vaqti qaysi soatda? (masalan, 15:00)"
- "25.04.2026" (vaqtsiz) → ask_more: "Qaysi soatga? (masalan, 18:00)"
- Foydalanuvchi "ha"/"yo'q" desa — tasdiqlash backend tomonida bo'ladi
"""

# Mini app uchun kontekst bilan kengaytirilgan prompt
WEBAPP_SYSTEM_PROMPT = """Siz TaskBot AI yordamchisisiz. Foydalanuvchi o'zbek, rus yoki aralash tilda yozishi mumkin.
Siz uni tushunib, O'ZBEK TILIDA javob berasiz.

Quyidagi hollarda FAQAT JSON qaytaring (hech qanday qo'shimcha matn yozmang):

1. VAZIFA YARATISH JARAYONI — IKKI BOSQICHLI:

  1.A) Agar foydalanuvchi vazifa yaratmoqchi BO'LSA-YU, lekin kerakli ma'lumot YETMASA
  (kamida: NOMI, TAVSIFI, MUHIMLIK, DEADLINE — DEADLINE MAJBURIY!), savol bering:
  {"action":"ask_more","text":"Yo'q ma'lumotni so'ragan savol o'zbek tilida","draft":{"title":"...yoki null","description":"...yoki null","priority":"low|medium|high|urgent yoki null","deadline":"YYYY-MM-DD HH:MM yoki null"}}

  Bir savolda faqat 1-2 ta ma'lumot so'rang. Misollar:
  - Foydalanuvchi: "yangi vazifa qo'sh" → siz: ask_more — "Vazifa nima haqida? Nomini yozing."
  - Foydalanuvchi: "hisobot yoz" → siz: ask_more — "Yaxshi! Tavsifini ham qisqacha yozing — nima haqidagi hisobot?"
  - Tavsif olindi → ask_more — "Muhimlik darajasi qanday? (past/o'rta/yuqori/muhim)"
  - Muhimlik olindi → ask_more — "Deadline qachon? Sanani va vaqtni yozing (masalan: ertaga 15:00)"

  Har safar `draft` ichida shu paytgacha to'plangan barcha ma'lumotni saqlang.

  1.B) Agar BARCHA 4 ta ma'lumot to'plangan bo'lsa (title, description, priority, deadline — barchasi to'liq),
  YARATMASDAN, foydalanuvchidan TASDIQ so'rang:
  {"action":"propose_task","title":"vazifa nomi","description":"to'liq tavsif","priority":"low|medium|high|urgent","deadline":"YYYY-MM-DD HH:MM"}

  HECH QACHON `propose_task` ni `deadline=null` bilan qaytarmang!
  HECH QACHON `description=null` bilan qaytarmang — bo'sh bo'lsa qaytadan so'rang.

2. VAZIFALAR RO'YXATI:
{"action":"list_tasks","filter":"all|active|done|urgent|overdue"}

3. STATISTIKA:
{"action":"show_stats"}

4. STATUS O'ZGARTIRISH:
{"action":"update_task","task_ref":"nom yoki ID","new_status":"in_progress|done|review|cancelled"}

5. QIDIRUV:
{"action":"search_tasks","query":"so'z"}

6. O'CHIRISH:
{"action":"delete_task","task_ref":"nom yoki ID"}

7. ODDIY JAVOB:
{"action":"reply","text":"javob o'zbek tilida"}

MUHIM QOIDALAR:
- FAQAT JSON qaytaring
- Vazifa yaratishda DEADLINE va TAVSIF MAJBURIY — yo'q bo'lsa ask_more bilan so'rang
- DEADLINE da SANA VA VAQT IKKALASI HAM bo'lishi kerak (HH:MM)
- Faqat sana aytilsa (vaqtsiz) — ask_more bilan VAQTNI so'rang
- HECH QACHON deadline ni "YYYY-MM-DD" formatida (vaqtsiz) qaytarmang
- HECH QACHON deadline ni "00:00" ga avtomatik qo'ymang
- Vazifani O'ZINGIZ yaratmang — har doim foydalanuvchi tasdiqlashi shart (propose_task)
- "ertaga 15:00" → ertangi sana 15:00 ✅
- "ertaga" (vaqtsiz) → ask_more: "Vaqti qaysi soatda? (masalan: 15:00)"
- "25.04.2026" (vaqtsiz) → ask_more: "Qaysi soatga? (masalan: 18:00)"
- Foydalanuvchi "ha", "tasdiqlayman", "yarat" desa ham — siz uni tasdiqlamang, frontend uni qabul qiladi
- Foydalanuvchi "yo'q", "bekor" desa — {"action":"reply","text":"Yaxshi, bekor qildim."}
"""


class AIService:

    @staticmethod
    def get_client() -> Optional[AsyncGroq]:
        if not settings.GROQ_API_KEY:
            return None
        return AsyncGroq(api_key=settings.GROQ_API_KEY)

    @staticmethod
    async def transcribe_voice(file_path: str) -> Optional[str]:
        """Ovoz faylini matnga aylantirish (Whisper)"""
        client = AIService.get_client()
        if not client:
            return None
        try:
            with open(file_path, "rb") as f:
                transcription = await client.audio.transcriptions.create(
                    file=(os.path.basename(file_path), f),
                    model="whisper-large-v3-turbo",
                    response_format="text",
                )
            return str(transcription).strip()
        except Exception as e:
            logger.error(f"Transcription xatosi: {e}")
            return None

    @staticmethod
    async def process_message(text: str, user_name: str, history: list = None) -> dict:
        """Bot handler uchun (suhbat tarixi bilan)"""
        client = AIService.get_client()
        if not client:
            return {"action": "reply", "text": "AI xizmati sozlanmagan."}

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        system_full = SYSTEM_PROMPT + f"\n\nHozirgi vaqt: {now}\nFoydalanuvchi: {user_name}"

        messages = [{"role": "system", "content": system_full}]
        if history:
            for h in history[-10:]:
                role = h.get("role", "user")
                if role in ("user", "assistant"):
                    messages.append({"role": role, "content": h.get("content", "")})
        messages.append({"role": "user", "content": text})

        try:
            response = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.3,
                max_tokens=500,
            )
            content = response.choices[0].message.content.strip()
            if content.startswith("{"):
                return json.loads(content)
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
            return {"action": "reply", "text": content}
        except json.JSONDecodeError:
            return {"action": "reply", "text": content}
        except Exception as e:
            logger.error(f"AI xatosi: {e}")
            return {"action": "reply", "text": "Xatolik yuz berdi. Qaytadan urining."}

    @staticmethod
    async def process_message_with_context(
        text: str,
        user_name: str,
        tasks_ctx: list,
        stats_ctx: dict,
        history: list,
    ) -> dict:
        """Mini app uchun kontekst (vazifalar, statistika) va tarix bilan qayta ishlash"""
        client = AIService.get_client()
        if not client:
            return {"action": "reply", "text": "AI xizmati sozlanmagan."}

        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Vazifalar ro'yxatini kontekst sifatida qo'shamiz
        STATUS_UZ = {
            "new": "Yangi", "in_progress": "Jarayonda", "done": "Bajarildi",
            "overdue": "Kechikdi", "review": "Ko'rilmoqda", "cancelled": "Bekor",
        }
        PRIORITY_UZ = {"low": "Past", "medium": "O'rta", "high": "Yuqori", "urgent": "Muhim"}

        task_lines = []
        for t in tasks_ctx[:50]:
            st = STATUS_UZ.get(t.get("status", ""), t.get("status", ""))
            pr = PRIORITY_UZ.get(t.get("priority", ""), t.get("priority", ""))
            dl = ""
            if t.get("deadline"):
                try:
                    dl = " | " + t["deadline"][:16]
                except Exception:
                    pass
            task_lines.append(f"ID:{t['id']} | {t['title']} | {st} | {pr}{dl}")

        stats_line = (
            f"Jami: {stats_ctx.get('total', 0)}, "
            f"Bajarildi: {stats_ctx.get('done', 0)}, "
            f"Jarayonda: {stats_ctx.get('in_progress', 0)}, "
            f"Yangi: {stats_ctx.get('new', 0)}, "
            f"Kechikdi: {stats_ctx.get('overdue', 0)}"
        )

        context_block = (
            f"Hozirgi vaqt: {now}\n"
            f"Foydalanuvchi: {user_name}\n"
            f"Statistika: {stats_line}\n\n"
            f"Foydalanuvchining vazifalari ({len(task_lines)} ta):\n"
            + ("\n".join(task_lines) if task_lines else "Vazifalar yo'q")
        )

        system_content = WEBAPP_SYSTEM_PROMPT + "\n\n---\n" + context_block

        messages = [{"role": "system", "content": system_content}]
        # Oxirgi 8 ta xabar (4 turn) ni qo'shamiz
        for h in history[-8:]:
            role = h.get("role", "user")
            if role in ("user", "assistant"):
                messages.append({"role": role, "content": h["content"]})
        messages.append({"role": "user", "content": text})

        try:
            response = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.25,
                max_tokens=600,
            )
            content = response.choices[0].message.content.strip()
            # JSON ni ajratib olish
            if content.startswith("{"):
                return json.loads(content)
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
            return {"action": "reply", "text": content}
        except json.JSONDecodeError:
            return {"action": "reply", "text": content}
        except Exception as e:
            logger.error(f"AI (context) xatosi: {e}")
            return {"action": "reply", "text": "Xatolik yuz berdi. Qaytadan urining."}
