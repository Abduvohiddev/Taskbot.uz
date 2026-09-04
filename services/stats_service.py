"""
Statistics service - statistika va hisobotlar
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    Task, TaskStatus, TaskAssignment, User, GroupMember, Group
)

logger = logging.getLogger(__name__)

_TZ = ZoneInfo("Asia/Tashkent")
_UTC = ZoneInfo("UTC")


class StatsService:
    """Statistika va hisobotlar xizmati"""
    
    @staticmethod
    async def get_user_stats(
        session: AsyncSession,
        user_id: int,
        days: int = 30,  # orqaga mos kelish uchun saqlanadi, lekin ishlatilmaydi
    ) -> Dict:
        """Foydalanuvchi statistikasi — joriy oy asosida"""
        import calendar
        now_tz = datetime.now(_TZ)
        # Joriy oyning boshidan hisoblash
        since = datetime(now_tz.year, now_tz.month, 1, tzinfo=_TZ).astimezone(_UTC)
        now = datetime.now(_UTC)

        # Per-user assignment status bo'yicha sanash —
        # FAQAT mas'ul + Task.status DONE bo'lsa hisobga olinadi (TaskAssignment yangilanmasa ham)
        eff_status = case(
            (Task.status == TaskStatus.DONE, "done"),
            else_=TaskAssignment.status,
        )
        result = await session.execute(
            select(eff_status.label("st"), func.count(TaskAssignment.id))
            .join(Task, TaskAssignment.task_id == Task.id)
            .where(
                and_(
                    TaskAssignment.user_id == user_id,
                    TaskAssignment.is_responsible.is_(True),
                    Task.created_at >= since,
                )
            )
            .group_by(eff_status)
        )
        asg_counts = {row[0]: row[1] for row in result.all()}

        done = asg_counts.get("done", 0)
        in_progress = asg_counts.get("in_progress", 0) + asg_counts.get("review", 0)
        new_cnt = asg_counts.get("new", 0)

        # Overdue: foydalanuvchining o'zi bajarmagan va deadline o'tgan — faqat mas'ul
        overdue_res = await session.execute(
            select(func.count(TaskAssignment.id))
            .join(Task, TaskAssignment.task_id == Task.id)
            .where(
                and_(
                    TaskAssignment.user_id == user_id,
                    TaskAssignment.is_responsible.is_(True),
                    TaskAssignment.status != "done",
                    Task.deadline.isnot(None),
                    Task.deadline < now,
                    Task.created_at >= since,
                )
            )
        )
        overdue = overdue_res.scalar() or 0

        total = sum(asg_counts.values())
        completion_rate = (done / total * 100) if total > 0 else 0

        return {
            "total": total,
            "done": done,
            "overdue": overdue,
            "in_progress": in_progress,
            "new": new_cnt,
            "completion_rate": round(completion_rate, 1),
            "status_counts": {"done": done, "in_progress": in_progress, "new": new_cnt, "overdue": overdue},
        }
    
    @staticmethod
    async def get_group_member_stats(
        session: AsyncSession,
        group_id: int,
        days: int = 30,
    ) -> List[Dict]:
        """Guruh a'zolari bo'yicha statistika"""
        since = datetime.now(_UTC) - timedelta(days=days)
        
        members_result = await session.execute(
            select(User)
            .join(GroupMember, GroupMember.user_id == User.id)
            .where(GroupMember.group_id == group_id)
        )
        members = list(members_result.scalars().all())
        
        stats = []
        for user in members:
            result = await session.execute(
                select(Task.status, func.count(Task.id))
                .join(TaskAssignment, TaskAssignment.task_id == Task.id)
                .where(
                    and_(
                        TaskAssignment.user_id == user.id,
                        Task.group_id == group_id,
                        Task.created_at >= since,
                    )
                )
                .group_by(Task.status)
            )
            status_counts = {row[0].value: row[1] for row in result.all()}
            
            stats.append({
                "user_id": user.id,
                "user_name": user.full_name,
                "done": status_counts.get("done", 0),
                "overdue": status_counts.get("overdue", 0),
                "in_progress": status_counts.get("in_progress", 0),
                "new": status_counts.get("new", 0),
                "total": sum(status_counts.values()),
            })
        
        stats.sort(key=lambda x: x["total"], reverse=True)
        return stats

    @staticmethod
    async def get_company_member_stats(
        session: AsyncSession,
        company_id: int,
    ) -> List[Dict]:
        """Kompaniya a'zolari statistika + reyting bali"""
        from database.models import CompanyMember, Company

        members_res = await session.execute(
            select(User, CompanyMember)
            .join(CompanyMember, CompanyMember.user_id == User.id)
            .where(CompanyMember.company_id == company_id)
        )
        members = list(members_res.all())

        now = datetime.now(_UTC)
        stats = []
        for user, member in members:
            # Per-user TaskAssignment statusi bo'yicha
            res = await session.execute(
                select(TaskAssignment.status, func.count(TaskAssignment.id))
                .join(Task, TaskAssignment.task_id == Task.id)
                .where(
                    and_(
                        TaskAssignment.user_id == user.id,
                        Task.company_id == company_id,
                    )
                )
                .group_by(TaskAssignment.status)
            )
            sc = {row[0]: row[1] for row in res.all()}
            done       = sc.get("done", 0)
            in_progress= sc.get("in_progress", 0) + sc.get("review", 0)
            new        = sc.get("new", 0)
            total      = sum(sc.values())
            ov_res = await session.execute(
                select(func.count(TaskAssignment.id))
                .join(Task, TaskAssignment.task_id == Task.id)
                .where(
                    and_(
                        TaskAssignment.user_id == user.id,
                        TaskAssignment.status != "done",
                        Task.deadline.isnot(None),
                        Task.deadline < now,
                        Task.company_id == company_id,
                    )
                )
            )
            overdue = ov_res.scalar() or 0
            score      = max(0, done * 10 - overdue * 8 + in_progress * 2)
            rate       = round(done / total * 100) if total else 0

            stats.append({
                "user_id": user.id,
                "user_name": member.display_name or user.full_name,
                "role": member.role.value,
                "done": done,
                "overdue": overdue,
                "in_progress": in_progress,
                "new": new,
                "total": total,
                "score": score,
                "completion_rate": rate,
            })

        stats.sort(key=lambda x: x["score"], reverse=True)
        for i, s in enumerate(stats):
            s["rank"] = i + 1
        return stats

    @staticmethod
    async def get_user_priority_stats(
        session: AsyncSession,
        user_id: int,
        company_id: Optional[int] = None,
    ) -> Dict:
        """Foydalanuvchi vazifalarining muhimlik taqsimoti"""
        stmt = (
            select(Task.priority, func.count(Task.id))
            .join(TaskAssignment, TaskAssignment.task_id == Task.id)
            .where(TaskAssignment.user_id == user_id)
            .group_by(Task.priority)
        )
        if company_id:
            stmt = stmt.where(Task.company_id == company_id)
        res = await session.execute(stmt)
        return {row[0].value: row[1] for row in res.all()}
    
    @staticmethod
    async def get_weekly_dynamics(
        session: AsyncSession,
        group_id: Optional[int] = None,
        user_id: Optional[int] = None,
        company_id: Optional[int] = None,
    ) -> List[Dict]:
        """Oylik dinamika - joriy oyning har kuni yaratilgan va bajarilgan"""
        import calendar
        now_tz = datetime.now(_TZ)
        days_data = []

        # Joriy oyning 1-sanasidan bugungi kungacha
        for day_num in range(1, now_tz.day + 1):
            from datetime import date as _date
            local_day = _date(now_tz.year, now_tz.month, day_num)
            day_start = datetime.combine(local_day, datetime.min.time(), tzinfo=_TZ).astimezone(_UTC)
            day_end = datetime.combine(local_day, datetime.max.time(), tzinfo=_TZ).astimezone(_UTC)

            created_query = select(func.count(Task.id)).where(
                Task.created_at.between(day_start, day_end)
            )
            completed_query = select(func.count(Task.id)).where(
                Task.completed_at.between(day_start, day_end)
            )

            if company_id:
                created_query = created_query.where(Task.company_id == company_id)
                completed_query = completed_query.where(Task.company_id == company_id)

            if group_id:
                created_query = created_query.where(Task.group_id == group_id)
                completed_query = completed_query.where(Task.group_id == group_id)

            if user_id:
                created_query = created_query.join(
                    TaskAssignment, TaskAssignment.task_id == Task.id
                ).where(TaskAssignment.user_id == user_id)
                completed_query = completed_query.join(
                    TaskAssignment, TaskAssignment.task_id == Task.id
                ).where(TaskAssignment.user_id == user_id)
            
            created_count = (await session.execute(created_query)).scalar() or 0
            completed_count = (await session.execute(completed_query)).scalar() or 0
            
            days_data.append({
                "date": local_day.strftime("%d.%m"),
                "day": str(day_num),
                "created": created_count,
                "done": completed_count,
            })
        
        return days_data
    
    @staticmethod
    async def get_user_daily_report_data(
        session: AsyncSession,
        user_id: int,
    ) -> List[Dict]:
        """
        Foydalanuvchining barcha kompaniyalari bo'yicha hisobot:
        har bir kompaniya uchun status taqsimoti qaytaradi.
        """
        from database.models import Company, CompanyMember, Group, GroupMember
        from sqlalchemy import or_

        now = datetime.now(_UTC)

        # Barcha kompaniyalarni topish (to'g'ridan-to'g'ri + guruh orqali)
        direct_subq = (
            select(CompanyMember.company_id)
            .where(CompanyMember.user_id == user_id)
            .scalar_subquery()
        )
        via_group_subq = (
            select(Group.company_id)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(
                GroupMember.user_id == user_id,
                Group.company_id.isnot(None),
            )
            .scalar_subquery()
        )
        companies_res = await session.execute(
            select(Company)
            .where(or_(Company.id.in_(direct_subq), Company.id.in_(via_group_subq)))
            .order_by(Company.name)
        )
        companies = list(companies_res.scalars().all())

        report = []
        for company in companies:
            # Effective status — Task.status DONE bo'lsa har holda done deb hisoblanadi
            # (chunki ba'zan TaskAssignment.status yangilanmasdan qoladi)
            eff_status = case(
                (Task.status == TaskStatus.DONE, "done"),
                else_=TaskAssignment.status,
            )
            sc_res = await session.execute(
                select(eff_status.label("st"), func.count(TaskAssignment.id))
                .join(Task, TaskAssignment.task_id == Task.id)
                .where(
                    and_(
                        TaskAssignment.user_id == user_id,
                        TaskAssignment.is_responsible.is_(True),
                        Task.company_id == company.id,
                    )
                )
                .group_by(eff_status)
            )
            sc = {row[0]: row[1] for row in sc_res.all()}

            done        = sc.get("done", 0)
            in_progress = sc.get("in_progress", 0) + sc.get("review", 0)
            new_cnt     = sc.get("new", 0)
            total       = sum(sc.values())

            if total == 0:
                continue

            # Kechikkan: Task.status DONE emas + deadline o'tgan + mas'ul
            ov_res = await session.execute(
                select(func.count(TaskAssignment.id))
                .join(Task, TaskAssignment.task_id == Task.id)
                .where(
                    and_(
                        TaskAssignment.user_id == user_id,
                        TaskAssignment.is_responsible.is_(True),
                        Task.company_id == company.id,
                        Task.status != TaskStatus.DONE,
                        TaskAssignment.status != "done",
                        Task.deadline.isnot(None),
                        Task.deadline < now,
                    )
                )
            )
            overdue = ov_res.scalar() or 0

            report.append({
                "company_id":       company.id,
                "company_name":     company.name,
                "total":            total,
                "done":             done,
                "in_progress":      in_progress,
                "new":              new_cnt,
                "overdue":          overdue,
                "completion_rate":  round(done / total * 100) if total else 0,
                "status_counts": {
                    "done":        done,
                    "in_progress": in_progress,
                    "new":         new_cnt,
                    "overdue":     overdue,
                },
            })

        return report

    @staticmethod
    async def get_completion_report(
        session: AsyncSession,
        group_id: Optional[int] = None,
        days: int = 7,
    ) -> Dict:
        """Bajarilish hisoboti"""
        since = datetime.now(_UTC) - timedelta(days=days)
        
        query = select(func.count(Task.id)).where(Task.created_at >= since)
        if group_id:
            query = query.where(Task.group_id == group_id)
        total_created = (await session.execute(query)).scalar() or 0
        
        query = select(func.count(Task.id)).where(
            and_(
                Task.completed_at.isnot(None),
                Task.completed_at >= since,
            )
        )
        if group_id:
            query = query.where(Task.group_id == group_id)
        total_completed = (await session.execute(query)).scalar() or 0
        
        query = select(func.count(Task.id)).where(
            Task.status == TaskStatus.OVERDUE
        )
        if group_id:
            query = query.where(Task.group_id == group_id)
        total_overdue = (await session.execute(query)).scalar() or 0
        
        query = select(
            func.avg(
                func.extract('epoch', Task.completed_at - Task.created_at) / 3600
            )
        ).where(
            and_(
                Task.completed_at.isnot(None),
                Task.completed_at >= since,
            )
        )
        if group_id:
            query = query.where(Task.group_id == group_id)
        avg_hours = (await session.execute(query)).scalar() or 0
        
        return {
            "period_days": days,
            "total_created": total_created,
            "total_completed": total_completed,
            "total_overdue": total_overdue,
            "avg_completion_hours": round(float(avg_hours), 1) if avg_hours else 0,
            "completion_rate": round(
                (total_completed / total_created * 100) if total_created > 0 else 0, 1
            ),
        }
