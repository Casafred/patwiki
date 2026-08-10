"""单专利 Wiki 式只读分享。"""
from datetime import datetime, timezone
import secrets
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Patent, PatentShare
from app.core.exceptions import NotFoundException

router = APIRouter(tags=["patent-shares"])


class PatentShareCreate(BaseModel):
    title_override: Optional[str] = None
    expires_at: Optional[datetime] = None


class PatentShareOut(BaseModel):
    id: int
    patent_id: int
    token: str
    title_override: Optional[str] = None
    is_active: bool
    expires_at: Optional[datetime] = None
    access_count: int
    last_accessed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    share_path: str


def _normalise_expiry(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _is_expired(share: PatentShare) -> bool:
    return share.expires_at is not None and share.expires_at <= datetime.now(timezone.utc).replace(tzinfo=None)


def _share_out(share: PatentShare) -> PatentShareOut:
    return PatentShareOut(
        id=share.id,
        patent_id=share.patent_id,
        token=share.token,
        title_override=share.title_override,
        is_active=bool(share.is_active),
        expires_at=share.expires_at,
        access_count=share.access_count or 0,
        last_accessed_at=share.last_accessed_at,
        created_at=share.created_at,
        updated_at=share.updated_at,
        share_path=f"/share/patents/{share.token}",
    )


@router.post("/patents/{patent_id}/shares", response_model=PatentShareOut)
def create_patent_share(
    patent_id: int,
    share_in: PatentShareCreate,
    db: Session = Depends(get_db),
):
    patent = db.query(Patent).filter(Patent.id == patent_id).first()
    if not patent:
        raise NotFoundException("Patent not found")

    share = PatentShare(
        patent_id=patent_id,
        token=secrets.token_urlsafe(32),
        title_override=(share_in.title_override or "").strip() or None,
        expires_at=_normalise_expiry(share_in.expires_at),
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    return _share_out(share)


@router.get("/patents/{patent_id}/shares", response_model=list[PatentShareOut])
def list_patent_shares(patent_id: int, db: Session = Depends(get_db)):
    if not db.query(Patent.id).filter(Patent.id == patent_id).first():
        raise NotFoundException("Patent not found")
    shares = db.query(PatentShare).filter(
        PatentShare.patent_id == patent_id,
    ).order_by(PatentShare.id.desc()).all()
    return [_share_out(share) for share in shares]


@router.delete("/patents/{patent_id}/shares/{token}")
def revoke_patent_share(patent_id: int, token: str, db: Session = Depends(get_db)):
    share = db.query(PatentShare).filter(
        PatentShare.patent_id == patent_id,
        PatentShare.token == token,
    ).first()
    if not share:
        raise NotFoundException("Share link not found")
    share.is_active = False
    db.commit()
    return {"success": True, "token": token}


def _enum_value(value):
    return value.value if hasattr(value, "value") else value


def _public_patent_payload(patent: Patent) -> dict:
    """只暴露适合技术主题分享的字段，不公开内部 AI/custom JSON。"""
    basic_fields = (
        "application_number", "publication_number", "grant_number", "applicant",
        "inventor", "assignee", "agent", "filing_date", "publication_date",
        "grant_date", "priority_date", "priority_number", "priority_country",
        "country", "patent_type", "legal_status", "legal_status_date",
        "ipc_main", "ipc_all", "cpc_main", "cpc_all",
    )
    technical_fields = (
        "abstract", "category", "subcategory", "module", "technical_problem",
        "technical_solution", "technical_effect", "scope_description", "claims",
        "has_risk", "risk_level", "risk_description",
    )
    payload = {"id": patent.id, "title": patent.title}
    for field in (*basic_fields, *technical_fields):
        value = getattr(patent, field, None)
        payload[field] = _enum_value(value)
    payload["tags"] = [{"id": tag.id, "name": tag.name, "color": tag.color} for tag in patent.tags]
    payload["projects"] = [{"id": project.id, "name": project.name} for project in patent.projects]
    return payload


@router.get("/share/patents/{token}")
def get_public_patent_share(token: str, db: Session = Depends(get_db)):
    share = db.query(PatentShare).options(
        joinedload(PatentShare.patent).joinedload(Patent.tags),
        joinedload(PatentShare.patent).joinedload(Patent.projects),
    ).filter(PatentShare.token == token).first()
    if not share or not share.is_active or _is_expired(share):
        raise NotFoundException("Share link not found or expired")

    share.access_count = (share.access_count or 0) + 1
    share.last_accessed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return {
        "share": _share_out(share),
        "patent": {
            **_public_patent_payload(share.patent),
            "title": share.title_override or share.patent.title,
        },
    }
