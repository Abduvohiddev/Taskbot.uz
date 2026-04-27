"""
Kompaniya (Workspace) xizmati - Company bilan ishlash logikasi
"""
from typing import Optional, List
import uuid

from sqlalchemy import select
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
        """Foydalanuvchi qatnashadigan barcha kompaniyalarni olish"""
        result = await session.execute(
            select(Company)
            .join(CompanyMember, CompanyMember.company_id == Company.id)
            .where(CompanyMember.user_id == user_id)
            .order_by(Company.name)
        )
        return list(result.scalars().all())

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
    async def generate_new_invite(session: AsyncSession, company_id: int) -> Optional[str]:
        """Yangi taklif kodini yaratish"""
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if company:
            company.invite_code = str(uuid.uuid4())[:12]
            await session.flush()
            return company.invite_code
        return None
