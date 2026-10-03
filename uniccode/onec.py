"""
1C OData dan nomenklatura katalogini olish (faqat o'qish).

GET <ONEC_BASE_URL>/Catalog_Номенклатура?$filter=IsFolder eq false and DeletionMark eq false
    &$select=Ref_Key,Артикул,Description,НаименованиеПолное&$orderby=Ref_Key&$top=1000&$skip=N
$orderby majburiy: tartibsiz sahifalashda 1C yozuvlarni takrorlaydi va tushirib qoldiradi.
1C ba'zan bir necha daqiqa "Информационная база не обнаружена" deb javob beradi - shuning uchun qayta urinish bor.
Marka (qo'shimcha rekvizit) hozircha OData tarkibida yo'q - katalogdagi bor markaga tegilmaydi.
"""
import asyncio
import logging
import re
from typing import Dict, Optional, Tuple

import aiohttp

from uniccode.generator import normalize_article

log = logging.getLogger("uniccode.onec")
ENTITY = "Catalog_Номенклатура"


class OneCError(Exception):
    pass


async def _get_page(session: aiohttp.ClientSession, url: str, params: dict, retries: int, delay: float) -> list:
    last = None
    for attempt in range(retries + 1):
        try:
            async with session.get(url, params=params) as resp:
                text = await resp.text()
                if resp.status == 401:
                    raise OneCError("1C: login yoki parol noto'g'ri (401)")
                if resp.status != 200:
                    raise aiohttp.ClientResponseError(resp.request_info, (), status=resp.status, message=text[:200])
                data = await resp.json(content_type=None)
                return data.get("value", [])
        except OneCError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            last = e
            if attempt < retries:
                wait = delay * (2 ** attempt)
                log.warning("1C so'rovi xato (%s), %s s dan keyin qayta: %s", attempt + 1, wait, e)
                await asyncio.sleep(wait)
    raise OneCError(f"1C javob bermadi: {type(last).__name__}: {str(last)[:200]}")


async def fetch_catalog(base_url: str, user: str, password: str, page: int = 1000,
                        retries: int = 4, delay: float = 5.0, timeout: float = 120.0) -> Dict[str, Tuple[str, Optional[str]]]:
    """{artikul: (nomi, None)} - papka va o'chirilganlarsiz, faqat 6 xonali artikullar."""
    url = base_url.rstrip("/") + "/" + ENTITY
    auth = aiohttp.BasicAuth(user, password, encoding="utf-8") if user else None  # login'da o', g' bo'lishi mumkin
    out: Dict[str, Tuple[str, Optional[str]]] = {}
    skip = 0
    async with aiohttp.ClientSession(auth=auth, timeout=aiohttp.ClientTimeout(total=timeout)) as session:
        while True:
            params = {
                "$format": "json",
                "$filter": "IsFolder eq false and DeletionMark eq false",
                "$select": "Ref_Key,Артикул,Description,НаименованиеПолное",
                "$orderby": "Ref_Key",
                "$top": str(page),
                "$skip": str(skip),
            }
            rows = await _get_page(session, url, params, retries, delay)
            for r in rows:
                art = normalize_article(r.get("Артикул"))
                name = (r.get("НаименованиеПолное") or r.get("Description") or "").strip()
                if re.match(r"^\d{6}$", art) and name and art not in out:
                    out[art] = (name[:255], None)
            if len(rows) < page:
                break
            skip += page
    return out
