from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class MaterialFamily(Base):
    """Broad polymer family, for example Polyamide, PETG or Styrenic."""

    __tablename__ = "material_families"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    color_hex: Mapped[str] = mapped_column(String(16), default="#64748b")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    variants: Mapped[list["MaterialVariant"]] = relationship(
        back_populates="family",
        cascade="all, delete-orphan",
        order_by="MaterialVariant.short_name",
    )


class MaterialVariant(Base):
    """
    Specific printable material variant, for example PA6-CF, ASA or PETG.

    This is deliberately separate from a manufacturer product. Multiple brands
    can sell products based on the same generic material variant.
    """

    __tablename__ = "material_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(
        ForeignKey("material_families.id", ondelete="RESTRICT"),
        index=True,
    )
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    short_name: Mapped[str] = mapped_column(String(120))
    full_name: Mapped[str] = mapped_column(String(260))
    classification: Mapped[str] = mapped_column(
        String(120),
        default="Base polymer",
    )
    formula: Mapped[str] = mapped_column(String(300), default="")
    repeat_unit: Mapped[str] = mapped_column(String(500), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    best_for: Mapped[str] = mapped_column(Text, default="")
    avoid_for: Mapped[str] = mapped_column(Text, default="")
    source_notes: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    family: Mapped["MaterialFamily"] = relationship(back_populates="variants")
    property_records: Mapped[list["MaterialPropertyRecord"]] = relationship(
        back_populates="material_variant",
        cascade="all, delete-orphan",
        order_by="MaterialPropertyRecord.id.desc()",
    )


class PropertyDefinition(Base):
    """
    Definition of an engineering property, for example tensile_strength or hdt.

    Definitions are shared. Actual measured or published values live in
    MaterialPropertyRecord, where each value carries its own source and state.
    """

    __tablename__ = "property_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(180))
    category: Mapped[str] = mapped_column(String(80), default="General")
    value_type: Mapped[str] = mapped_column(String(40), default="numeric")
    default_unit: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    records: Mapped[list["MaterialPropertyRecord"]] = relationship(
        back_populates="property_definition",
        cascade="all, delete-orphan",
    )


class MaterialPropertyRecord(Base):
    """
    One sourced property value for one material variant.

    Several records may exist for the same property: dry, conditioned, wet,
    manufacturer TDS, paper, literature or personal measurement.
    """

    __tablename__ = "material_property_records"
    __table_args__ = (
        Index(
            "ix_material_property_records_variant_property",
            "material_variant_id",
            "property_definition_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_variant_id: Mapped[int] = mapped_column(
        ForeignKey("material_variants.id", ondelete="CASCADE"),
        index=True,
    )
    property_definition_id: Mapped[int] = mapped_column(
        ForeignKey("property_definitions.id", ondelete="RESTRICT"),
        index=True,
    )

    value_number: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str] = mapped_column(Text, default="")
    unit: Mapped[str] = mapped_column(String(80), default="")

    material_state: Mapped[str] = mapped_column(String(40), default="unknown")
    test_condition: Mapped[str] = mapped_column(Text, default="")
    test_standard: Mapped[str] = mapped_column(String(160), default="")

    source_type: Mapped[str] = mapped_column(
        String(80),
        default="manufacturer_tds",
    )
    source_title: Mapped[str] = mapped_column(String(300), default="")
    source_url: Mapped[str] = mapped_column(String(1000), default="")
    confidence: Mapped[str] = mapped_column(String(40), default="medium")

    observed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    material_variant: Mapped["MaterialVariant"] = relationship(
        back_populates="property_records",
    )
    property_definition: Mapped["PropertyDefinition"] = relationship(
        back_populates="records",
    )
