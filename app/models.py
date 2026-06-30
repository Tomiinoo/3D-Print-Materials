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
    spool_code: Mapped[str] = mapped_column(String(60), default="")
    spool_weight_g: Mapped[float] = mapped_column(Float, default=1000)
    notes: Mapped[str] = mapped_column(Text, default="")
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
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


class PrinterPreset(Base):
    __tablename__ = "printer_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(String(260), default="")
    printer_type: Mapped[str] = mapped_column(String(80), default="FDM / FFF")
    nozzle_max_c: Mapped[float] = mapped_column(Float, default=300)
    bed_max_c: Mapped[float] = mapped_column(Float, default=100)
    chamber_max_c: Mapped[float] = mapped_column(Float, default=0)
    enclosed: Mapped[bool] = mapped_column(Boolean, default=False)
    heated_chamber: Mapped[bool] = mapped_column(Boolean, default=False)
    direct_drive: Mapped[bool] = mapped_column(Boolean, default=True)
    supports_flexible: Mapped[bool] = mapped_column(Boolean, default=True)
    ams_capable: Mapped[bool] = mapped_column(Boolean, default=False)
    build_volume: Mapped[str] = mapped_column(String(120), default="")
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    serial_number: Mapped[str] = mapped_column(String(120), default="")
    hours_before_tracking: Mapped[float] = mapped_column(Float, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    print_profiles: Mapped[list["PrintProfile"]] = relationship(back_populates="printer")
    nozzles: Mapped[list["PrinterNozzle"]] = relationship(
        back_populates="printer",
        cascade="all, delete-orphan",
        order_by="PrinterNozzle.installed.desc(), PrinterNozzle.id.desc()",
    )
    maintenance_entries: Mapped[list["PrinterMaintenance"]] = relationship(
        back_populates="printer",
        cascade="all, delete-orphan",
        order_by="PrinterMaintenance.maintenance_date.desc(), PrinterMaintenance.id.desc()",
    )


class PrinterNozzle(Base):
    __tablename__ = "printer_nozzles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    printer_id: Mapped[int] = mapped_column(ForeignKey("printer_presets.id"), index=True)
    label: Mapped[str] = mapped_column(String(180))
    diameter_mm: Mapped[float] = mapped_column(Float, default=0.4)
    nozzle_material: Mapped[str] = mapped_column(String(60), default="brass")
    brand_product: Mapped[str] = mapped_column(String(180), default="")
    installed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    installed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    hours_before_tracking: Mapped[float] = mapped_column(Float, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    printer: Mapped["PrinterPreset"] = relationship(back_populates="nozzles")
    print_profiles: Mapped[list["PrintProfile"]] = relationship(back_populates="printer_nozzle")


class PrinterMaintenance(Base):
    __tablename__ = "printer_maintenance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    printer_id: Mapped[int] = mapped_column(ForeignKey("printer_presets.id"), index=True)
    maintenance_date: Mapped[date] = mapped_column(Date, default=date.today)
    maintenance_type: Mapped[str] = mapped_column(String(60), default="service")
    component: Mapped[str] = mapped_column(String(180), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    cost_eur: Mapped[float | None] = mapped_column(Float, nullable=True)
    printer_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    printer: Mapped["PrinterPreset"] = relationship(back_populates="maintenance_entries")


class PrintProfile(Base):
    __tablename__ = "print_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("filament_products.id"), nullable=True, index=True)
    printer_id: Mapped[int | None] = mapped_column(ForeignKey("printer_presets.id"), nullable=True, index=True)
    printer_nozzle_id: Mapped[int | None] = mapped_column(ForeignKey("printer_nozzles.id"), nullable=True, index=True)
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
    filament_used_g: Mapped[float] = mapped_column(Float, default=0)
    print_duration_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    result_rating: Mapped[int] = mapped_column(Integer, default=3)
    notes: Mapped[str] = mapped_column(Text, default="")
    printed_on: Mapped[date] = mapped_column(Date, default=date.today)

    material: Mapped["Material"] = relationship(back_populates="print_profiles")
    product: Mapped["FilamentProduct | None"] = relationship(back_populates="print_profiles")
    printer: Mapped["PrinterPreset | None"] = relationship(back_populates="print_profiles")
    printer_nozzle: Mapped["PrinterNozzle | None"] = relationship(back_populates="print_profiles")
    attachments: Mapped[list["PrintAttachment"]] = relationship(
        back_populates="print_profile",
        cascade="all, delete-orphan",
        order_by="PrintAttachment.uploaded_at.desc(), PrintAttachment.id.desc()",
    )


class PrintAttachment(Base):
    __tablename__ = "print_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    print_profile_id: Mapped[int] = mapped_column(ForeignKey("print_profiles.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(260))
    stored_relative_path: Mapped[str] = mapped_column(String(500), unique=True)
    file_category: Mapped[str] = mapped_column(String(20))
    mime_type: Mapped[str] = mapped_column(String(120), default="")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    print_profile: Mapped["PrintProfile"] = relationship(back_populates="attachments")
