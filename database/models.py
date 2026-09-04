"""
SQLAlchemy modellari - barcha jadvallar
"""
import enum
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Optional

from sqlalchemy import (
    BigInteger, String, Text, DateTime, ForeignKey, Integer,
    Enum as SQLEnum, Boolean, JSON, UniqueConstraint, Index
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from config import settings


class Base(DeclarativeBase):
    """Barcha modellar uchun asos klass"""
    pass


class TaskStatus(str, enum.Enum):
    """Vazifa statuslari"""
    NEW = "new"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class Priority(str, enum.Enum):
    """Muhimlik darajasi"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class UserRole(str, enum.Enum):
    """Guruhdagi foydalanuvchi roli"""
    ADMIN = "admin"
    MANAGER = "manager"
    EXECUTOR = "executor"


class CompanyRole(str, enum.Enum):
    """Kompaniyadagi xodim roli"""
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class NotificationType(str, enum.Enum):
    """Bildirishnoma turlari"""
    TASK_ASSIGNED = "task_assigned"
    TASK_STATUS_CHANGED = "task_status_changed"
    DEADLINE_WARNING = "deadline_warning"
    DEADLINE_URGENT = "deadline_urgent"
    TASK_OVERDUE = "task_overdue"
    TASK_COMMENT = "task_comment"
    DAILY_REPORT = "daily_report"


class User(Base):
    """Foydalanuvchilar jadvali"""
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(100))
    full_name: Mapped[str] = mapped_column(String(200))
    language: Mapped[str] = mapped_column(String(5), default="uz")
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Tashkent")
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_hr: Mapped[bool] = mapped_column(Boolean, default=False)
    is_feedback_admin: Mapped[bool] = mapped_column(Boolean, default=False)  # Murojaat admini
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=False)  # AI maslahatchi (admin yoqadi)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    
    group_memberships: Mapped[List["GroupMember"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    company_memberships: Mapped[List["CompanyMember"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    created_tasks: Mapped[List["Task"]] = relationship(
        back_populates="creator", foreign_keys="Task.creator_id"
    )
    assignments: Mapped[List["TaskAssignment"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    comments: Mapped[List["TaskComment"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    notifications: Mapped[List["Notification"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<User id={self.id} telegram_id={self.telegram_id}>"


class Company(Base):
    """Kompaniyalar (Workspacelar) jadvali"""
    __tablename__ = "companies"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    invite_code: Mapped[Optional[str]] = mapped_column(String(50), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    owner: Mapped["User"] = relationship(foreign_keys=[owner_id])
    members: Mapped[List["CompanyMember"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    groups: Mapped[List["Group"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    tasks: Mapped[List["Task"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<Company id={self.id} name={self.name}>"


class CompanyMember(Base):
    """Kompaniya xodimlari"""
    __tablename__ = "company_members"
    __table_args__ = (
        UniqueConstraint("company_id", "user_id", name="uq_company_user"),
        Index("ix_company_members_company_id", "company_id"),
        Index("ix_company_members_user_id", "user_id"),
    )
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[CompanyRole] = mapped_column(SQLEnum(CompanyRole, values_callable=lambda x: [e.name for e in x]), default=CompanyRole.MEMBER)
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="company_memberships")
    
    def __repr__(self) -> str:
        return f"<CompanyMember company={self.company_id} user={self.user_id} role={self.role}>"


class Group(Base):
    """Guruhlar (workspacelar) jadvali"""
    __tablename__ = "groups"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_group_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Tashkent")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_blocked_by_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped[Optional["Company"]] = relationship(back_populates="groups")
    owner: Mapped["User"] = relationship(foreign_keys=[owner_id])
    members: Mapped[List["GroupMember"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    tasks: Mapped[List["Task"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<Group id={self.id} name={self.name}>"


class GroupMember(Base):
    """Guruh a'zolari - User va Group orasidagi many-to-many"""
    __tablename__ = "group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_group_user"),
        Index("ix_group_members_group_id", "group_id"),
        Index("ix_group_members_user_id", "user_id"),
    )
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("groups.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole, values_callable=lambda x: [e.name for e in x]), default=UserRole.EXECUTOR)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    group: Mapped["Group"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="group_memberships")
    
    def __repr__(self) -> str:
        return f"<GroupMember group={self.group_id} user={self.user_id} role={self.role}>"


class Task(Base):
    """Vazifalar jadvali"""
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_deadline", "deadline"),
        Index("ix_tasks_group_id", "group_id"),
    )
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus, values_callable=lambda x: [e.name for e in x]),
        default=TaskStatus.NEW,
    )
    priority: Mapped[Priority] = mapped_column(
        SQLEnum(Priority, values_callable=lambda x: [e.name for e in x]),
        default=Priority.MEDIUM,
    )
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    creator_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    company_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="CASCADE")
    )
    group_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("groups.id", ondelete="CASCADE")
    )
    parent_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE")
    )
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Eslatma flaglari (har biri faqat 1 marta yuboriladi)
    warned_24h: Mapped[bool] = mapped_column(Boolean, default=False)   # Ertalabki 8:00 eslatmasi
    warned_4h: Mapped[bool] = mapped_column(Boolean, default=False)    # 3 soat qoldi
    warned_2h: Mapped[bool] = mapped_column(Boolean, default=False)    # 2 soat qoldi
    warned_1h: Mapped[bool] = mapped_column(Boolean, default=False)    # 1 soat qoldi
    warned_exact: Mapped[bool] = mapped_column(Boolean, default=False) # Aynan vaqtida
    
    creator: Mapped["User"] = relationship(back_populates="created_tasks", foreign_keys=[creator_id])
    company: Mapped[Optional["Company"]] = relationship(back_populates="tasks")
    group: Mapped[Optional["Group"]] = relationship(back_populates="tasks")
    assignments: Mapped[List["TaskAssignment"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    comments: Mapped[List["TaskComment"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    history: Mapped[List["TaskHistory"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    attachments: Mapped[List["TaskAttachment"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    steps: Mapped[List["TaskStep"]] = relationship(
        back_populates="task", cascade="all, delete-orphan",
        order_by="TaskStep.order_index",
    )
    subtasks: Mapped[List["Task"]] = relationship(
        back_populates="parent", foreign_keys="Task.parent_id",
        cascade="all, delete-orphan",
    )
    parent: Mapped[Optional["Task"]] = relationship(
        back_populates="subtasks", foreign_keys="Task.parent_id",
        remote_side="Task.id",
    )
    
    @property
    def is_overdue(self) -> bool:
        """Vazifa kechikdimi?"""
        if not self.deadline or self.status in (TaskStatus.DONE, TaskStatus.CANCELLED):
            return False
        
        _TZ = ZoneInfo(settings.DEFAULT_TIMEZONE)
        now = datetime.now(_TZ)
        deadline = self.deadline
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=_TZ)
        else:
            deadline = deadline.astimezone(_TZ)
            
        return now > deadline
    
    def __repr__(self) -> str:
        return f"<Task id={self.id} title={self.title[:30]} status={self.status}>"


class TaskAssignment(Base):
    """Vazifa ijrochilari - Task va User orasidagi many-to-many"""
    __tablename__ = "task_assignments"
    __table_args__ = (
        UniqueConstraint("task_id", "user_id", name="uq_task_user"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default="new")
    is_responsible: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Vaqt kuzatuvi: jarayonga tushganda boshlanadi, bajarilganda to'xtaydi
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)  # started→done sekundlarda

    task: Mapped["Task"] = relationship(back_populates="assignments")
    user: Mapped["User"] = relationship(back_populates="assignments")


class TaskComment(Base):
    """Vazifaga yozilgan izohlar"""
    __tablename__ = "task_comments"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    task: Mapped["Task"] = relationship(back_populates="comments")
    user: Mapped["User"] = relationship(back_populates="comments")


class TaskAttachment(Base):
    """Vazifaga biriktirilgan fayl yoki rasm"""
    __tablename__ = "task_attachments"
    __table_args__ = (
        Index("ix_task_attachments_task_id", "task_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    file_type: Mapped[str] = mapped_column(String(20), default="document")  # photo/document/video
    file_id: Mapped[Optional[str]] = mapped_column(String(500))  # Telegram file_id
    file_name: Mapped[Optional[str]] = mapped_column(String(500))
    file_url: Mapped[Optional[str]] = mapped_column(String(1000))  # local url
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped["Task"] = relationship(back_populates="attachments")
    user: Mapped["User"] = relationship()


class TaskStep(Base):
    """Vazifaning ketma-ket bosqichi (workflow).
    Har bir qadam — alohida ijrochi va o'z holati. Faqat tartib bilan
    aktivlashadi: oldingisi 'done' bo'lmaguncha keyingisi 'pending'.
    """
    __tablename__ = "task_steps"
    __table_args__ = (
        Index("ix_task_steps_task_id", "task_id"),
        Index("ix_task_steps_assignee", "assignee_user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"))
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(500))
    assignee_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    # status: pending (navbati kelmagan) / active (hozir bajarilmoqda) / done / skipped
    status: Mapped[str] = mapped_column(String(20), default="pending")
    note: Mapped[Optional[str]] = mapped_column(Text)  # bajarilganda izoh
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # NISBIY MUDDAT: qadam aktivlashganda deadline = aktivlashgan vaqt + duration_days.
    # Shu tufayli oldingi qadam kechiksa ham, bu odam o'z to'liq muddatini oladi.
    duration_days: Mapped[Optional[int]] = mapped_column(Integer)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Workflow qadam eslatma flaglari
    step_warned_morning: Mapped[bool] = mapped_column(Boolean, default=False)
    step_warned_3h: Mapped[bool] = mapped_column(Boolean, default=False)
    step_warned_2h: Mapped[bool] = mapped_column(Boolean, default=False)
    step_warned_1h: Mapped[bool] = mapped_column(Boolean, default=False)
    step_warned_exact: Mapped[bool] = mapped_column(Boolean, default=False)

    task: Mapped["Task"] = relationship(back_populates="steps")
    assignee: Mapped["User"] = relationship()
    comments: Mapped[List["TaskStepComment"]] = relationship(
        back_populates="step", cascade="all, delete-orphan",
        order_by="TaskStepComment.created_at",
    )
    attachments: Mapped[List["TaskStepAttachment"]] = relationship(
        back_populates="step", cascade="all, delete-orphan",
        order_by="TaskStepAttachment.created_at",
    )


class TaskStepComment(Base):
    """Workflow qadamiga yozilgan izoh"""
    __tablename__ = "task_step_comments"
    __table_args__ = (Index("ix_task_step_comments_step", "step_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    step_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("task_steps.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    step: Mapped["TaskStep"] = relationship(back_populates="comments")
    user: Mapped["User"] = relationship()


class TaskStepAttachment(Base):
    """Workflow qadamiga biriktirilgan fayl"""
    __tablename__ = "task_step_attachments"
    __table_args__ = (Index("ix_task_step_attachments_step", "step_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    step_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("task_steps.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    file_type: Mapped[str] = mapped_column(String(20), default="document")
    file_id: Mapped[Optional[str]] = mapped_column(String(500))
    file_url: Mapped[Optional[str]] = mapped_column(String(500))   # Mini App orqali yuklangan fayl
    file_name: Mapped[Optional[str]] = mapped_column(String(500))
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    step: Mapped["TaskStep"] = relationship(back_populates="attachments")
    user: Mapped["User"] = relationship()


class TaskHistory(Base):
    """Vazifa o'zgarishlari tarixi (audit log)"""
    __tablename__ = "task_history"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(50))
    old_value: Mapped[Optional[dict]] = mapped_column(JSON)
    new_value: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    task: Mapped["Task"] = relationship(back_populates="history")
    user: Mapped["User"] = relationship()


class Notification(Base):
    """Yuborilgan bildirishnomalar"""
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_id", "user_id"),
        Index("ix_notifications_is_read", "is_read"),
    )
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[NotificationType] = mapped_column(SQLEnum(NotificationType, values_callable=lambda x: [e.name for e in x]))
    message: Mapped[str] = mapped_column(Text)
    task_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE")
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    user: Mapped["User"] = relationship(back_populates="notifications")


class HRDocument(Base):
    """HR hujjatlari — lavozim yo'riqnomalari"""
    __tablename__ = "hr_documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(300))
    image_path: Mapped[Optional[str]] = mapped_column(String(500))          # birinchi rasm (backward compat)
    images_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # JSON array of all image paths
    extracted_text: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(100), default="hradmin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Eslatma — javob bermaganlarga har kuni belgilangan soatda so'raladi;
    # har N kunda esa hamma (tasdiqlagan/rad etgan) qaytadan tasdiqlaydi.
    remind_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    remind_time: Mapped[Optional[str]] = mapped_column(String(5))   # "HH:MM" (Asia/Tashkent)
    remind_reopen: Mapped[bool] = mapped_column(Boolean, default=False)  # (eski, ishlatilmaydi)
    remind_interval_days: Mapped[int] = mapped_column(Integer, default=0)  # 0 = qayta ochilmaydi
    last_reopen_on: Mapped[Optional[str]] = mapped_column(String(10))      # "YYYY-MM-DD"

    assignments: Mapped[List["HRAssignment"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class HRAssignmentStatus(str, enum.Enum):
    PENDING   = "pending"
    CONFIRMED = "confirmed"
    REJECTED  = "rejected"


class HRAssignment(Base):
    """HR hujjatlarini foydalanuvchilarga biriktirish"""
    __tablename__ = "hr_assignments"
    __table_args__ = (
        UniqueConstraint("document_id", "user_id", name="uq_hr_doc_user"),
        Index("ix_hr_assignments_user_id", "user_id"),
        Index("ix_hr_assignments_document_id", "document_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_documents.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(
        String(20),
        default=HRAssignmentStatus.PENDING.value,
    )
    comment: Mapped[Optional[str]] = mapped_column(Text)
    telegram_message_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_reminded_on: Mapped[Optional[str]] = mapped_column(String(10))  # "YYYY-MM-DD" — kunlik takrorni oldini oladi

    document: Mapped["HRDocument"] = relationship(back_populates="assignments")
    user: Mapped["User"] = relationship()


# ═══════════════════════════════════════════════════════════════
#  MUROJAAT (taklif / shikoyat) moduli
# ═══════════════════════════════════════════════════════════════

class FeedbackType(str, enum.Enum):
    """Murojaat turi"""
    COMPLAINT = "complaint"     # Shikoyat
    SUGGESTION = "suggestion"   # Taklif


class FeedbackStatus(str, enum.Enum):
    """Murojaat holati"""
    PENDING = "pending"       # Yangi — ko'rib chiqilmoqda
    IN_REVIEW = "in_review"   # Ko'rib chiqilmoqda (admin ochgan)
    RESOLVED = "resolved"     # Yechim berildi


class Feedback(Base):
    """Foydalanuvchi murojaatlari — taklif yoki shikoyat (anonim/oshkora)"""
    __tablename__ = "feedbacks"
    __table_args__ = (
        Index("ix_feedbacks_user_id", "user_id"),
        Index("ix_feedbacks_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(20), default=FeedbackType.SUGGESTION.value)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=FeedbackStatus.PENDING.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    attachments: Mapped[List["FeedbackAttachment"]] = relationship(
        back_populates="feedback", cascade="all, delete-orphan"
    )
    replies: Mapped[List["FeedbackReply"]] = relationship(
        back_populates="feedback", cascade="all, delete-orphan",
        order_by="FeedbackReply.created_at",
    )
    discussions: Mapped[List["FeedbackDiscussion"]] = relationship(
        back_populates="feedback", cascade="all, delete-orphan",
        order_by="FeedbackDiscussion.created_at",
    )


class FeedbackAttachment(Base):
    """Murojaatga biriktirilgan mediya (rasm/video/fayl)"""
    __tablename__ = "feedback_attachments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    feedback_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("feedbacks.id", ondelete="CASCADE"))
    file_id: Mapped[Optional[str]] = mapped_column(String(300))   # Telegram file_id (bot oqimi)
    file_url: Mapped[Optional[str]] = mapped_column(String(500))  # Server fayl URL (Mini App oqimi)
    file_type: Mapped[str] = mapped_column(String(20), default="document")
    file_name: Mapped[Optional[str]] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    feedback: Mapped["Feedback"] = relationship(back_populates="attachments")


class FeedbackReply(Base):
    """Murojaatga admin javobi"""
    __tablename__ = "feedback_replies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    feedback_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("feedbacks.id", ondelete="CASCADE"))
    admin_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.id"))  # HR panel uchun null bo'lishi mumkin
    admin_name: Mapped[Optional[str]] = mapped_column(String(200))  # javob bergan (ko'rsatish uchun)
    source: Mapped[Optional[str]] = mapped_column(String(20), default="admin")  # admin | hr
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    feedback: Mapped["Feedback"] = relationship(back_populates="replies")
    admin: Mapped["User"] = relationship(foreign_keys=[admin_id])


class FeedbackDiscussion(Base):
    """Murojaatni muhokamaga yo'naltirish — HR tomonidan biror userga.

    HR shikoyat/taklifni bir yoki bir nechta odamga muhokama uchun yuboradi
    (izoh bilan). O'sha odam javob beradi yoki rad etadi.
    """
    __tablename__ = "feedback_discussions"
    __table_args__ = (
        Index("ix_feedback_discussions_feedback_id", "feedback_id"),
        Index("ix_feedback_discussions_target", "target_user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    feedback_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("feedbacks.id", ondelete="CASCADE"))
    target_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    hr_comment: Mapped[Optional[str]] = mapped_column(Text)          # HR ning yo'naltirishdagi izohi
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | answered | rejected
    response: Mapped[Optional[str]] = mapped_column(Text)            # userning javobi yoki rad sababi
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    feedback: Mapped["Feedback"] = relationship(back_populates="discussions")
    target_user: Mapped["User"] = relationship(foreign_keys=[target_user_id])


class Reminder(Base):
    """AI maslahatchi tomonidan qo'yilgan eslatmalar.

    Foydalanuvchi AI bilan "bu vazifani palon vaqtda eslat" desa, AI shu yozuvni
    yaratadi. Scheduler belgilangan vaqtda motivatsion xabar bilan eslatadi.
    """
    __tablename__ = "reminders"
    __table_args__ = (
        Index("ix_reminders_due", "remind_at", "is_sent"),
        Index("ix_reminders_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    task_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"))
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    text: Mapped[str] = mapped_column(Text)              # nimani eslatish
    is_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    task: Mapped[Optional["Task"]] = relationship(foreign_keys=[task_id])
