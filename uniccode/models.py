"""@uniccodebot jadvallari. Asosiy Taskbot jadvallaridan alohida metadata (uc_ prefiksi)."""
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class UCBase(DeclarativeBase):
    pass


class UCCounter(UCBase):
    """Har bir artikul uchun oxirgi berilgan tartib raqam."""
    __tablename__ = "uc_counters"

    article: Mapped[str] = mapped_column(String(16), primary_key=True)
    last_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UCBatch(UCBase):
    """Bitta so'rov (buyruq yoki fayl) natijasida yasalgan kodlar to'plami."""
    __tablename__ = "uc_batches"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    username: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(32))  # kod | sklad | royxat | import
    filename: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text)
    count: Mapped[int] = mapped_column(Integer, default=0)


class UCCode(UCBase):
    """Har bir unikal kod. code ustuni noyob: bir xil kod ikki marta yozilmaydi."""
    __tablename__ = "uc_codes"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    article: Mapped[str] = mapped_column(String(16), nullable=False)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(String(255))       # Датабаза E ustuni (adres, partiya...)
    address: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str | None] = mapped_column(String(255))
    series: Mapped[str | None] = mapped_column(String(128))     # konveyr / partiya
    machine: Mapped[str | None] = mapped_column(String(64))     # mashina (seriya fayli uchun)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("uc_batches.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(16), default="bot")  # bot | import
    synced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_uc_codes_article_seq", "article", "seq"),
        Index("ix_uc_codes_unsynced", "synced", "id"),
    )


class UCProduct(UCBase):
    """Mahsulot katalogi: artikul -> nomenklatura (seriya va RFID fayllari uchun)."""
    __tablename__ = "uc_products"

    article: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    marka: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
