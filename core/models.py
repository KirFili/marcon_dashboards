from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Chamber(Base):
    __tablename__ = "chambers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    temperature_c: Mapped[float] = mapped_column(Float)
    capacity_pallets: Mapped[int] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    value_type: Mapped[str] = mapped_column(String(20))  # int | float | str | bool
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Sku(Base):
    __tablename__ = "skus"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    supplier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chamber_id: Mapped[int | None] = mapped_column(
        ForeignKey("chambers.id"), nullable=True
    )
    # сырые поля 1С под расчёт паллет и скоуп
    group_kind: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Групировка по видам
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Единица хранения
    boxes_per_pallet: Mapped[int | None] = mapped_column(Integer, nullable=True)
    boxes_per_layer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    layers_per_pallet: Mapped[int | None] = mapped_column(Integer, nullable=True)
    units_per_box: Mapped[int | None] = mapped_column(Integer, nullable=True)
    units_per_pallet: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temp: Mapped[str | None] = mapped_column(String(50), nullable=True)  # ТемпературныйРежим
    company: Mapped[str | None] = mapped_column(String(50), nullable=True)  # КомпанияОтгрузки
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # opening | inbound | outbound | sku
    filename: Mapped[str] = mapped_column(String(255))
    file_hash: Mapped[str] = mapped_column(String(64), unique=True)
    row_count: Mapped[int] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Movement(Base):
    __tablename__ = "movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"))
    movement_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(20))  # opening | inbound | outbound
    boxes: Mapped[int] = mapped_column(Integer)
    upload_id: Mapped[int | None] = mapped_column(
        ForeignKey("uploads.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"))
    period: Mapped[date] = mapped_column(Date)  # первое число месяца
    revenue: Mapped[float] = mapped_column(Float)
    gross_profit: Mapped[float] = mapped_column(Float)
    upload_id: Mapped[int | None] = mapped_column(
        ForeignKey("uploads.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("sku_id", "period", name="uq_sales_sku_period"),)


class Stock(Base):
    __tablename__ = "stock"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"))
    period: Mapped[date] = mapped_column(Date)  # первое число месяца
    # остатки/движения за месяц, в единице хранения SKU
    opening: Mapped[float] = mapped_column(Float)
    inbound: Mapped[float] = mapped_column(Float)
    outbound: Mapped[float] = mapped_column(Float)
    closing: Mapped[float] = mapped_column(Float)
    upload_id: Mapped[int | None] = mapped_column(
        ForeignKey("uploads.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("sku_id", "period", name="uq_stock_sku_period"),)
