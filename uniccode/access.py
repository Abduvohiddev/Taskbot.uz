"""
Kim botdan foydalana oladi va panelda nimani ko'radi.

- superadmin: .env dagi UNIC_ADMIN_IDS - hamma narsa (barcha bo'limlar, foydalanuvchilar, sozlamalar).
- admin: panelda qo'shilgan bo'lim admini (chexol yoki polik) - o'z bo'limi dashboardi va o'z bo'limiga
  oddiy foydalanuvchi qo'shishi mumkin.
- user: botda kod yasaydi.
Ro'yxat xotirada saqlanadi va har o'zgarishda (va har daqiqada) bazadan yangilanadi.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from uniccode.config import UnicSettings
from uniccode.models import UCUser

SUPER, ADMIN, USER = "superadmin", "admin", "user"
DEPTS = ("chexol", "polik")
DEPT_NAMES = {"chexol": "Chexol", "polik": "Polik", None: "Hammasi"}
ROLE_NAMES = {SUPER: "Superadmin", ADMIN: "Bo'lim admini", USER: "Foydalanuvchi"}


@dataclass
class Who:
    tg_id: int
    role: str
    dept: Optional[str] = None
    name: str = ""

    @property
    def is_super(self) -> bool:
        return self.role == SUPER

    @property
    def can_panel(self) -> bool:
        return self.role in (SUPER, ADMIN)

    @property
    def scope(self) -> Optional[str]:
        """Dashboard qaysi bo'lim bo'yicha: None = hammasi."""
        return None if self.is_super else self.dept


class Access:
    def __init__(self, sm: async_sessionmaker, cfg: UnicSettings):
        self.sm = sm
        self.cfg = cfg
        self._users: Dict[int, UCUser] = {}

    async def refresh(self) -> None:
        async with self.sm() as s:
            rows = (await s.execute(select(UCUser))).scalars().all()
        self._users = {u.tg_id: u for u in rows}

    def who(self, uid: Optional[int]) -> Optional[Who]:
        if uid is None:
            return None
        if uid in self.cfg.admin_ids:
            return Who(uid, SUPER)
        u = self._users.get(uid)
        if u is not None:
            return Who(uid, u.role, u.dept, u.full_name) if u.active else None
        if uid in self.cfg.allowed_ids:
            return Who(uid, USER)
        if not self.cfg.allowed_ids and not self._users:   # hech kim sozlanmagan: ochiq rejim (eski xatti-harakat)
            return Who(uid, USER)
        return None

    def allowed(self, uid: Optional[int]) -> bool:
        return self.who(uid) is not None

    def is_super(self, uid: Optional[int]) -> bool:
        if not self.cfg.admin_ids:          # admin sozlanmagan: eski xatti-harakat - hamma admin
            return True
        w = self.who(uid)
        return bool(w and w.is_super)

    @staticmethod
    def can_manage(actor: Who, role: str, dept: Optional[str]) -> bool:
        """actor shu rol va bo'limdagi foydalanuvchini qo'sha/o'zgartira oladimi."""
        if actor.is_super:
            return role in (ADMIN, USER) and (dept in DEPTS or (dept is None and role == USER))
        return actor.role == ADMIN and role == USER and dept == actor.dept and dept is not None

    def users(self, actor: Who) -> List[UCUser]:
        rows = sorted(self._users.values(), key=lambda u: (u.dept or "", u.role, u.full_name.lower()))
        return rows if actor.is_super else [u for u in rows if u.dept == actor.dept]

    def get(self, tg_id: int) -> Optional[UCUser]:
        return self._users.get(tg_id)

    async def save_user(self, actor: Who, tg_id: int, full_name: str, role: str, dept: Optional[str]) -> str:
        """Qo'shadi yoki yangilaydi. Xato bo'lsa sababini qaytaradi, bo'lmasa bo'sh satr."""
        if tg_id in self.cfg.admin_ids:
            return "Bu ID superadmin (.env da) - panelda o'zgartirilmaydi."
        if not self.can_manage(actor, role, dept):
            return "Bu rol yoki bo'limga foydalanuvchi qo'shishga ruxsatingiz yo'q."
        old = self._users.get(tg_id)
        if old is not None and not self.can_manage(actor, old.role, old.dept):
            return "Bu foydalanuvchi boshqa bo'limda - uni o'zgartira olmaysiz."
        async with self.sm() as s:
            u = await s.get(UCUser, tg_id)
            if u is None:
                u = UCUser(tg_id=tg_id, added_by=actor.tg_id)
                s.add(u)
            u.full_name, u.role, u.dept, u.active = full_name.strip()[:128], role, dept, True
            await s.commit()
        await self.refresh()
        return ""

    async def set_active(self, actor: Who, tg_id: int, active: bool) -> str:
        u = self._users.get(tg_id)
        if u is None or not self.can_manage(actor, u.role, u.dept):
            return "Ruxsat yo'q."
        async with self.sm() as s:
            row = await s.get(UCUser, tg_id)
            row.active = active
            await s.commit()
        await self.refresh()
        return ""

    async def remove(self, actor: Who, tg_id: int) -> str:
        u = self._users.get(tg_id)
        if u is None or not self.can_manage(actor, u.role, u.dept):
            return "Ruxsat yo'q."
        async with self.sm() as s:
            await s.execute(delete(UCUser).where(UCUser.tg_id == tg_id))
            await s.commit()
        await self.refresh()
        return ""
