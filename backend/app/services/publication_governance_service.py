"""Publication number classification and system tags."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Patent, Tag, TagGroup
from app.services.patent_identity_service import normalize_publication_number, parse_identifier

SYSTEM_GROUP = "系统识别"
UNGRANTED_TAG = "未授权公开"
GRANTED_TEXT_TAG = "已有授权文本收录"


def publication_parts(value: str | None) -> tuple[str | None, str | None, str | None]:
    normalized = normalize_publication_number(value)
    if not normalized:
        return None, None, None
    spec = parse_identifier(normalized, "publication")
    if not spec:
        return None, None, None
    return normalized, spec.jurisdiction_code, (spec.kind_code or "").upper()


def _tag(db: Session, name: str) -> Tag:
    group = db.query(TagGroup).filter(TagGroup.name == SYSTEM_GROUP).first()
    if group is None:
        group = TagGroup(name=SYSTEM_GROUP, description="由系统根据专利公开号自动维护的标签")
        db.add(group)
        db.flush()
    item = db.query(Tag).filter(Tag.name == name, Tag.group_id == group.id).first()
    if item is None:
        item = Tag(name=name, group_id=group.id, description="自动识别标签")
        db.add(item)
        db.flush()
    return item


def classify_patent(db: Session, patent: Patent) -> bool:
    normalized, country, kind = publication_parts(patent.publication_number)
    changed = False
    if normalized and patent.publication_number != normalized:
        patent.publication_number = normalized
        changed = True
    if country and (not patent.country or patent.country == "CN") and patent.country != country:
        patent.country = country
        changed = True
    if not normalized:
        return changed
    ungranted = _tag(db, UNGRANTED_TAG)
    granted_text = _tag(db, GRANTED_TEXT_TAG)
    if kind.startswith("A"):
        if ungranted not in patent.tags:
            patent.tags.append(ungranted)
            changed = True
        peers = None
        if patent.application_number:
            peers = db.query(Patent).filter(Patent.id != patent.id, Patent.application_number == patent.application_number)
        elif patent.family_id:
            peers = db.query(Patent).filter(Patent.id != patent.id, Patent.family_id == patent.family_id)
        has_grant = bool(peers and any((publication_parts(peer.publication_number)[2] or "").startswith(("B", "C")) for peer in peers.all()))
        if has_grant and granted_text not in patent.tags:
            patent.tags.append(granted_text)
            changed = True
    elif kind.startswith(("B", "C")):
        if ungranted in patent.tags:
            patent.tags.remove(ungranted)
            changed = True
        peers = None
        if patent.application_number:
            peers = db.query(Patent).filter(Patent.id != patent.id, Patent.application_number == patent.application_number)
        elif patent.family_id:
            peers = db.query(Patent).filter(Patent.id != patent.id, Patent.family_id == patent.family_id)
        if peers:
            for peer in peers.all():
                peer_kind = (publication_parts(peer.publication_number)[2] or "")
                if peer_kind.startswith("A") and granted_text not in peer.tags:
                    peer.tags.append(granted_text)
                    changed = True
    return changed


def classify_database(db: Session, database_id: int) -> int:
    changed = sum(1 for patent in db.query(Patent).filter(Patent.database_id == database_id).all() if classify_patent(db, patent))
    db.commit()
    return changed
