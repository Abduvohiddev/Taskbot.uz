"""
Kompaniya (Workspace) xizmati - Company bilan ishlash logikasi
"""
from typing import Optional, List
import uuid

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Company, CompanyMember, CompanyRole, User


class CompanyService:
    
    @staticmethod
    async def create_company(session: AsyncSession, name: str, owner_id: int, description: Optional[str] = None) -> Company:
        """Yangi kompaniya yaratish va qatnashchini egasi (owner) sifatida qo'shish"""
        invite_code = str(uuid.uuid4())[:12]
        
        company = Company(
            name=name,
            description=description,
            owner_id=owner_id,
            invite_code=invite_code
        )
        session.add(company)
        await session.flush()
        
        # Egasi (Owner) sifatida qo'shish
        member = CompanyMember(
            company_id=company.id,
            user_id=owner_id,
            role=CompanyRole.OWNER
        )
        session.add(member)
        await session.flush()
        
        return company

    @staticmethod
    async def get_company(session: AsyncSession, company_id: int) -> Optional[Company]:
        """Kompaniyani ID bo'yicha olish"""
        result = await session.execute(
            select(Company)
            .where(Company.id == company_id)
            .options(selectinload(Company.owner), selectinload(Company.members).selectinload(CompanyMember.user))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_company_by_invite(session: AsyncSession, invite_code: str) -> Optional[Company]:
        """Kompaniyani taklif havolasi orqali topish"""
        result = await session.execute(
            select(Company).where(Company.invite_code == invite_code)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_companies(session: AsyncSession, user_id: int) -> List[Company]:
        """Foydalanuvchi qatnashadigan barcha kompaniyalarni olish.

        Ikkita yo'l bilan topiladi:
        1. CompanyMember jadvalida to'g'ridan-to'g'ri a'zolik
        2. GroupMember → Group.company_id orqali (guruh orqali qo'shilganlar)
        """
        from database.models import Group, GroupMember

        # 1) To'g'ridan-to'g'ri CompanyMember orqali
        direct_subq = (
            select(CompanyMember.company_id)
            .where(CompanyMember.user_id == user_id)
            .scalar_subquery()
        )

        # 2) GroupMember → Group.company_id orqali
        via_group_subq = (
            select(Group.company_id)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(
                GroupMember.user_id == user_id,
                Group.is_active == True,
                Group.company_id.isnot(None),
            )
            .scalar_subquery()
        )

        result = await session.execute(
            select(Company)
            .where(
                or_(
                    Company.id.in_(direct_subq),
                    Company.id.in_(via_group_subq),
                )
            )
            .order_by(Company.name)
        )
        companies = list(result.scalars().all())

        # Auto-sync: guruh orqali topilgan kompaniyalar uchun CompanyMember yo'q bo'lsa — qo'shamiz
        for company in companies:
            cm_check = await session.execute(
                select(CompanyMember).where(
                    CompanyMember.company_id == company.id,
                    CompanyMember.user_id == user_id,
                )
            )
            if not cm_check.scalar_one_or_none():
                session.add(CompanyMember(
                    company_id=company.id,
                    user_id=user_id,
                    role=CompanyRole.MEMBER,
                ))

        return companies

    @staticmethod
    async def repair_group_companies(session: AsyncSession, user_id: int) -> None:
        """Guruh bor lekin company_id=NULL bo'lgan guruhlar uchun kompaniya yaratadi.

        Foydalanuvchi guruh ADMIN bo'lsa — kompaniyani u OWNER sifatida yaratadi.
        EXECUTOR/MANAGER bo'lsa — kompaniya owneri sifatida guruh owner_id ishlatiladi,
        foydalanuvchi esa MEMBER sifatida qo'shiladi.
        """
        import logging
        from database.models import Group, GroupMember, UserRole
        _log = logging.getLogger(__name__)

        # Foydalanuvchi a'zo bo'lgan, ammo company_id yo'q guruhlar
        res = await session.execute(
            select(Group)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(
                GroupMember.user_id == user_id,
                Group.is_active == True,
                Group.company_id.is_(None),
            )
        )
        orphan_groups = res.scalars().all()

        for grp in orphan_groups:
            try:
                company = await CompanyService.create_company(
                    session, grp.name, grp.owner_id
                )
                grp.company_id = company.id
                await session.flush()

                # Guruhning barcha a'zolarini CompanyMember ga qo'shamiz
                gm_res = await session.execute(
                    select(GroupMember).where(GroupMember.group_id == grp.id)
                )
                for gm in gm_res.scalars().all():
                    cm_check = await session.execute(
                        select(CompanyMember).where(
                            CompanyMember.company_id == company.id,
                            CompanyMember.user_id == gm.user_id,
                        )
                    )
                    if not cm_check.scalar_one_or_none():
                        c_role = CompanyRole.OWNER if gm.user_id == grp.owner_id else CompanyRole.MEMBER
                        session.add(CompanyMember(
                            company_id=company.id,
                            user_id=gm.user_id,
                            role=c_role,
                        ))
                _log.info(f"Guruh {grp.id} uchun kompaniya yaratildi: {company.id}")
            except Exception as e:
                _log.warning(f"Guruh {grp.id} kompaniyasini yaratishda xato: {e}")

    @staticmethod
    async def add_member(session: AsyncSession, company_id: int, user_id: int, role: CompanyRole = CompanyRole.MEMBER) -> CompanyMember:
        """Kompaniyaga yangi foydalanuvchi qo'shish"""
        # Avval tekshiramiz
        result = await session.execute(
            select(CompanyMember)
            .where(CompanyMember.company_id == company_id, CompanyMember.user_id == user_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing
            
        member = CompanyMember(
            company_id=company_id,
            user_id=user_id,
            role=role
        )
        session.add(member)
        await session.flush()
        return member

    @staticmethod
    async def get_members(session: AsyncSession, company_id: int) -> List[CompanyMember]:
        """Kompaniya a'zolarini User bilan birga olish"""
        result = await session.execute(
            select(CompanyMember)
            .where(CompanyMember.company_id == company_id)
            .options(selectinload(CompanyMember.user))
            .order_by(CompanyMember.role, CompanyMember.joined_at)
        )
        return list(result.scalars().all())

    @staticmethod
    async def is_member(session: AsyncSession, company_id: int, user_id: int) -> Optional[CompanyRole]:
        """Foydalanuvchi kompaniyadami? Bo'lsa, rolini qaytaradi"""
        result = await session.execute(
            select(CompanyMember).where(
                CompanyMember.company_id == company_id,
                CompanyMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()
        return member.role if member else None

    @staticmethod
    async def rename_member(
        session: AsyncSession, company_id: int, user_id: int, new_name: str
    ) -> bool:
        """A'zoning company-ichidagi display_name'ini o'zgartirish"""
        result = await session.execute(
            select(CompanyMember).where(
                CompanyMember.company_id == company_id,
                CompanyMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            return False
        member.display_name = new_name.strip()[:200]
        await session.flush()
        return True

    @staticmethod
    async def remove_member(
        session: AsyncSession, company_id: int, user_id: int
    ) -> bool:
        """A'zoni kompaniyadan o'chirish (owner'ni o'chirib bo'lmaydi)"""
        result = await session.execute(
            select(CompanyMember).where(
                CompanyMember.company_id == company_id,
                CompanyMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()
        if not member or member.role == CompanyRole.OWNER:
            return False
        await session.delete(member)
        await session.flush()
        return True

    @staticmethod
    async def delete_company(session: AsyncSession, company_id: int, user_id: int) -> bool:
        """Kompaniyani to'liq o'chirish — faqat owner uchun"""
        result = await session.execute(
            select(Company).where(Company.id == company_id)
        )
        company = result.scalar_one_or_none()
        if not company or company.owner_id != user_id:
            return False
        await session.delete(company)
        await session.flush()
        return True

    @staticmethod
    async def generate_new_invite(session: AsyncSession, company_id: int) -> Optional[str]:
        """Yangi taklif kodini yaratish"""
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if company:
            company.invite_code = str(uuid.uuid4())[:12]
            await session.flush()
            return company.invite_code
        return None
