from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    full_name: Mapped[str] = mapped_column(String(260))
    family: Mapped[str] = mapped_column(String(120), index=True)
    subfamily: Mapped[str] = mapped_column(String(80), default="Base polymer")
    family_color: Mapped[str] = mapped_column(String(16), default="#64748b")
    formula: Mapped[str] = mapped_column(String(300), default="—")
    repeat_unit: Mapped[str] = mapped_column(String(500), default="—")
    description: Mapped[str] = mapped_column(Text, default="")
    best_for: Mapped[str] = mapped_column(Text, default="")
    avoid_for: Mapped[str] = mapped_column(Text, default="")
    settings_json: Mapped[str] = mapped_column(Text, default="{}")
    properties_json: Mapped[str] = mapped_column(Text, default="{}")
    source_notes: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    products: Mapped[list["FilamentProduct"]] = relationship(
        back_populates="material", cascade="all, delete-orphan", order_by="FilamentProduct.id.desc()"
    )
    print_profiles: Mapped[list["PrintProfile"]] = relationship(
        back_populates="material", cascade="all, delete-orphan", order_by="PrintProfile.id.desc()"
    )


class FilamentProduct(Base):
    __tablename__ = "filament_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    brand: Mapped[str] = mapped_column(String(120))
    product_name: Mapped[str] = mapped_column(String(180))
    supplier: Mapped[str] = mapped_column(String(160), default="")
    url: Mapped[str] = mapped_column(String(800), default="")
    color_name: Mapped[str] = mapped_column(String(80), default="")
    spool_weight_g: Mapped[float] = mapped_column(Float, default=1000)
    notes: Mapped[str] = mapped_column(Text, default="")
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    material: Mapped["Material"] = relationship(back_populates="products")
    price_entries: Mapped[list["PriceEntry"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", order_by="PriceEntry.observed_on.desc(), PriceEntry.id.desc()"
    )
    print_profiles: Mapped[list["PrintProfile"]] = relationship(back_populates="product")


class PriceEntry(Base):
    __tablename__ = "price_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("filament_products.id"), index=True)
    price_eur: Mapped[float] = mapped_column(Float)
    observed_on: Mapped[date] = mapped_column(Date, default=date.today)
    source_label: Mapped[str] = mapped_column(String(160), default="Manual entry")
    stock_note: Mapped[str] = mapped_column(String(240), default="")

    product: Mapped["FilamentProduct"] = relationship(back_populates="price_entries")


class PrintProfile(Base):
    __tablename__ = "print_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("filament_products.id"), nullable=True, index=True)
    profile_name: Mapped[str] = mapped_column(String(180))
    state: Mapped[str] = mapped_column(String(30), default="Dry")
    nozzle_diameter: Mapped[float] = mapped_column(Float, default=0.4)
    nozzle_temp: Mapped[float] = mapped_column(Float, default=0)
    bed_temp: Mapped[float] = mapped_column(Float, default=0)
    chamber_temp: Mapped[float] = mapped_column(Float, default=0)
    speed_mm_s: Mapped[float] = mapped_column(Float, default=0)
    dryer_temp: Mapped[float] = mapped_column(Float, default=0)
    dryer_hours: Mapped[float] = mapped_column(Float, default=0)
    build_plate: Mapped[str] = mapped_column(String(140), default="")
    result_rating: Mapped[int] = mapped_column(Integer, default=3)
    notes: Mapped[str] = mapped_column(Text, default="")
    printed_on: Mapped[date] = mapped_column(Date, default=date.today)

    material: Mapped["Material"] = relationship(back_populates="print_profiles")
    product: Mapped["FilamentProduct | None"] = relationship(back_populates="print_profiles")
