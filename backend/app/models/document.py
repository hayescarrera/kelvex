"""
Document model — uploaded file metadata linked to sites and/or equipment.

Actual file content lives in S3-compatible object storage (storage_key).
This table is the searchable, linkable record: what it is, where it lives, what it's about.

Types: utility_bill, maintenance_invoice, refrigerant_purchase, sla,
       equipment_manual, warranty, inspection_report, permit, other
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


DOCUMENT_TYPE_UTILITY_BILL = "utility_bill"
DOCUMENT_TYPE_MAINTENANCE_INVOICE = "maintenance_invoice"
DOCUMENT_TYPE_REFRIGERANT_PURCHASE = "refrigerant_purchase"
DOCUMENT_TYPE_SLA = "sla"
DOCUMENT_TYPE_EQUIPMENT_MANUAL = "equipment_manual"
DOCUMENT_TYPE_WARRANTY = "warranty"
DOCUMENT_TYPE_INSPECTION_REPORT = "inspection_report"
DOCUMENT_TYPE_PERMIT = "permit"
DOCUMENT_TYPE_OTHER = "other"


class Document(Base):
    """Metadata record for an uploaded document linked to a site and/or equipment."""

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_org", "org_id"),
        Index("ix_documents_facility", "facility_id"),
        Index("ix_documents_equipment", "equipment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    facility_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="SET NULL"), nullable=True
    )
    equipment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True
    )

    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)

    # S3-compatible storage key — never expose this directly to clients
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(nullable=True)

    # Searchable metadata: period dates, vendor, notes, tags
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True, default=dict)

    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self):
        return f"<Document {self.name} [{self.document_type}]>"
