"""
Documents API — upload, list, and delete file records linked to sites and equipment.

Endpoints:
  GET    /documents              — List documents (filterable by facility, type)
  POST   /documents              — Upload a document (multipart/form-data)
  DELETE /documents/{id}         — Delete document record and file
"""

import uuid
import aiofiles
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.facility import Facility
from app.models.document import Document
from app.services.audit_service import log_activity

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

ALLOWED_TYPES = {
    "utility_bill", "maintenance_invoice", "refrigerant_purchase",
    "sla", "equipment_manual", "warranty", "inspection_report", "permit", "other"
}


def _doc_to_dict(doc: Document) -> dict:
    return {
        "id": str(doc.id),
        "org_id": str(doc.org_id),
        "facility_id": str(doc.facility_id) if doc.facility_id else None,
        "equipment_id": str(doc.equipment_id) if doc.equipment_id else None,
        "document_type": doc.document_type,
        "name": doc.name,
        "storage_key": doc.storage_key,
        "content_type": doc.content_type,
        "size_bytes": doc.size_bytes,
        "metadata_": doc.metadata_,
        "uploaded_by": str(doc.uploaded_by) if doc.uploaded_by else None,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


async def _verify_facility(facility_id: UUID, user: User, db: AsyncSession) -> Facility:
    result = await db.execute(
        select(Facility).where(
            Facility.id == facility_id,
            Facility.org_id == user.org_id,
            Facility.deleted_at == None,
        )
    )
    fac = result.scalar_one_or_none()
    if not fac:
        raise HTTPException(status_code=404, detail="Facility not found")
    return fac


@router.get("")
async def list_documents(
    facility_id: UUID | None = Query(None),
    document_type: str | None = Query(None),
    equipment_id: UUID | None = Query(None),
    limit: int = Query(100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Document).where(Document.org_id == current_user.org_id)
    if facility_id:
        q = q.where(Document.facility_id == facility_id)
    if document_type:
        q = q.where(Document.document_type == document_type)
    if equipment_id:
        q = q.where(Document.equipment_id == equipment_id)
    q = q.order_by(Document.created_at.desc()).limit(limit)
    result = await db.execute(q)
    docs = result.scalars().all()
    return {"documents": [_doc_to_dict(d) for d in docs], "total": len(docs)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    name: str = Form(""),
    facility_id: UUID | None = Form(None),
    equipment_id: UUID | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if document_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid document_type. Allowed: {sorted(ALLOWED_TYPES)}")

    if facility_id:
        await _verify_facility(facility_id, current_user, db)

    content = await file.read()
    settings = get_settings()
    upload_dir = Path(settings.UPLOAD_DIR)
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB} MB limit")

    file_id = uuid.uuid4()
    org_dir = upload_dir / str(current_user.org_id)
    org_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename or "").suffix
    storage_key = f"{current_user.org_id}/{file_id}{ext}"
    dest = upload_dir / storage_key

    async with aiofiles.open(dest, "wb") as f:
        await f.write(content)

    display_name = name or file.filename or f"document{ext}"
    doc = Document(
        org_id=current_user.org_id,
        facility_id=facility_id,
        equipment_id=equipment_id,
        document_type=document_type,
        name=display_name,
        storage_key=storage_key,
        content_type=file.content_type,
        size_bytes=len(content),
        uploaded_by=current_user.id,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    await log_activity(
        db, user=current_user, org_id=current_user.org_id, action="create",
        resource_type="document", resource_id=str(doc.id), resource_name=display_name,
        facility_id=facility_id,
        summary=f"Uploaded {document_type}: {display_name} ({len(content) // 1024} KB)",
    )
    return _doc_to_dict(doc)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.org_id == current_user.org_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    upload_dir = Path(get_settings().UPLOAD_DIR)
    dest = upload_dir / doc.storage_key
    if dest.exists():
        dest.unlink(missing_ok=True)

    await log_activity(
        db, user=current_user, org_id=current_user.org_id, action="delete",
        resource_type="document", resource_id=str(doc.id), resource_name=doc.name,
        summary=f"Deleted document: {doc.name}",
    )
    await db.delete(doc)
    await db.commit()
