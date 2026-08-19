"""Transactional services for project solution context and risk tracking."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Iterable

from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import BadRequestException, ConflictException, NotFoundException
from app.models import (
    Patent,
    PatentDatabase,
    Project,
    ProjectSolutionChange,
    ProjectSolutionRegion,
    ProjectSolutionVersion,
    RiskAssessmentVersion,
    RiskCase,
    RiskCaseRegion,
    RiskPatentLink,
    RiskReviewEvent,
    RiskSolutionLink,
)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _require_database(db: Session, database_id: int) -> PatentDatabase:
    database = db.query(PatentDatabase).filter(PatentDatabase.id == database_id).first()
    if not database:
        raise NotFoundException("数据库不存在", database_id)
    return database


def _require_project(db: Session, project_id: int) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise NotFoundException("项目不存在", project_id)
    return project


def _next_version_no(db: Session, project_id: int) -> str:
    versions = db.query(ProjectSolutionVersion).filter(
        ProjectSolutionVersion.project_id == project_id,
    ).all()
    numbers = []
    for version in versions:
        try:
            numbers.append(int(version.version_no.removeprefix("v")))
        except (TypeError, ValueError):
            continue
    return f"v{max(numbers, default=0) + 1}"


def _solution_query(db: Session):
    return db.query(ProjectSolutionVersion).options(
        joinedload(ProjectSolutionVersion.changes),
        joinedload(ProjectSolutionVersion.regions),
    )


def list_solution_versions(db: Session, project_id: int, database_id: int | None = None):
    query = _solution_query(db).filter(ProjectSolutionVersion.project_id == project_id)
    if database_id is not None:
        query = query.filter(ProjectSolutionVersion.database_id == database_id)
    return query.order_by(ProjectSolutionVersion.id.desc()).all()


def get_solution_version(db: Session, solution_version_id: int) -> ProjectSolutionVersion:
    version = _solution_query(db).filter(ProjectSolutionVersion.id == solution_version_id).first()
    if not version:
        raise NotFoundException("项目方案版本不存在", solution_version_id)
    return version


def create_solution_version(db: Session, project_id: int, data) -> ProjectSolutionVersion:
    _require_project(db, project_id)
    _require_database(db, data.database_id)
    version_no = data.version_no or _next_version_no(db, project_id)
    existing = db.query(ProjectSolutionVersion).filter(
        ProjectSolutionVersion.project_id == project_id,
        ProjectSolutionVersion.version_no == version_no,
    ).first()
    if existing:
        raise ConflictException(f"项目方案版本号已存在：{version_no}")

    version = ProjectSolutionVersion(
        database_id=data.database_id,
        project_id=project_id,
        version_no=version_no,
        name=data.name,
        project_stage=data.project_stage,
        effective_from=data.effective_from,
        effective_to=data.effective_to,
        change_summary=data.change_summary,
        change_reason=data.change_reason,
        source_type=data.source_type,
        source_description=data.source_description,
        created_by=data.created_by or "local-user",
    )
    version.changes = [ProjectSolutionChange(**item.model_dump(), created_by=data.created_by or "local-user") for item in data.changes]
    version.regions = [ProjectSolutionRegion(**item.model_dump()) for item in data.regions]
    db.add(version)
    db.commit()
    return get_solution_version(db, version.id)


def update_solution_version(db: Session, solution_version_id: int, data) -> ProjectSolutionVersion:
    version = get_solution_version(db, solution_version_id)
    if version.status == "confirmed":
        raise ConflictException("已确认的方案版本不可原地修改，请创建新版本")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(version, field, value)
    db.commit()
    return get_solution_version(db, solution_version_id)


def confirm_solution_version(db: Session, solution_version_id: int, confirmed_by: str) -> ProjectSolutionVersion:
    version = get_solution_version(db, solution_version_id)
    if version.status == "confirmed":
        return version
    previous_versions = db.query(ProjectSolutionVersion).filter(
        ProjectSolutionVersion.project_id == version.project_id,
        ProjectSolutionVersion.id != version.id,
        ProjectSolutionVersion.status == "confirmed",
    ).all()
    for previous in previous_versions:
        previous.status = "superseded"
    version.status = "confirmed"
    version.confirmed_by = confirmed_by or "local-user"
    version.confirmed_at = _now()
    db.commit()
    return get_solution_version(db, solution_version_id)


def _validate_patents(db: Session, database_id: int, patent_ids: Iterable[int]) -> list[Patent]:
    ids = list(dict.fromkeys(patent_ids))
    patents = db.query(Patent).filter(Patent.id.in_(ids)).all() if ids else []
    found = {patent.id: patent for patent in patents}
    missing = [patent_id for patent_id in ids if patent_id not in found]
    if missing:
        raise NotFoundException(f"专利不存在：{missing}")
    mismatched = [patent.id for patent in patents if patent.database_id not in (None, database_id)]
    if mismatched:
        raise BadRequestException(f"专利与风险案例不属于同一数据库：{mismatched}")
    return patents


def _validate_solution_links(db: Session, database_id: int, solution_ids: Iterable[int]) -> list[ProjectSolutionVersion]:
    ids = list(dict.fromkeys(solution_ids))
    versions = db.query(ProjectSolutionVersion).filter(ProjectSolutionVersion.id.in_(ids)).all() if ids else []
    found = {version.id: version for version in versions}
    missing = [solution_id for solution_id in ids if solution_id not in found]
    if missing:
        raise NotFoundException(f"方案版本不存在：{missing}")
    mismatched = [version.id for version in versions if version.database_id != database_id]
    if mismatched:
        raise BadRequestException(f"方案版本与风险案例不属于同一数据库：{mismatched}")
    return versions


def _risk_query(db: Session):
    return db.query(RiskCase).options(
        joinedload(RiskCase.patent_links),
        joinedload(RiskCase.solution_links),
        joinedload(RiskCase.regions),
        joinedload(RiskCase.assessments),
        joinedload(RiskCase.reviews),
    )


def list_risk_cases(db: Session, database_id: int, patent_id: int | None = None, status: str | None = None):
    _require_database(db, database_id)
    query = _risk_query(db).filter(RiskCase.database_id == database_id)
    if patent_id is not None:
        query = query.join(RiskPatentLink).filter(RiskPatentLink.patent_id == patent_id)
    if status:
        query = query.filter(RiskCase.status == status)
    return query.order_by(RiskCase.updated_at.desc(), RiskCase.id.desc()).all()


def get_risk_case(db: Session, risk_case_id: int) -> RiskCase:
    risk_case = _risk_query(db).filter(RiskCase.id == risk_case_id).first()
    if not risk_case:
        raise NotFoundException("风险案例不存在", risk_case_id)
    return risk_case


def create_risk_case(db: Session, data) -> RiskCase:
    _require_database(db, data.database_id)
    if not data.patent_links:
        raise BadRequestException("风险案例至少需要关联一篇专利")
    _validate_patents(db, data.database_id, [item.patent_id for item in data.patent_links])
    _validate_solution_links(db, data.database_id, [item.solution_version_id for item in data.solution_links])
    risk_case = RiskCase(
        database_id=data.database_id,
        case_no=data.case_no,
        title=data.title,
        trigger_reason=data.trigger_reason,
        current_gate=data.current_gate,
        notes=data.notes,
        created_by=data.created_by or "local-user",
    )
    risk_case.patent_links = [RiskPatentLink(**item.model_dump()) for item in data.patent_links]
    risk_case.solution_links = [RiskSolutionLink(**item.model_dump()) for item in data.solution_links]
    risk_case.regions = [RiskCaseRegion(**item.model_dump()) for item in data.regions]
    db.add(risk_case)
    db.commit()
    return get_risk_case(db, risk_case.id)


def update_risk_case(db: Session, risk_case_id: int, data) -> RiskCase:
    risk_case = get_risk_case(db, risk_case_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(risk_case, field, value)
    db.commit()
    return get_risk_case(db, risk_case_id)


def add_risk_assessment(db: Session, risk_case_id: int, data) -> RiskCase:
    risk_case = get_risk_case(db, risk_case_id)
    is_draft = data.decision == "pending"
    linked_solution_ids = {item.solution_version_id for item in risk_case.solution_links}
    if data.solution_version_id is not None and data.solution_version_id not in linked_solution_ids:
        raise BadRequestException("评估所选方案版本必须先关联到当前风险案例")
    if not is_draft:
        required = {
            "solution_version_id": data.solution_version_id,
            "jurisdiction_code": data.jurisdiction_code,
            "assessed_by": data.assessed_by,
            "confirmed_by": data.confirmed_by,
            "decision_basis": data.decision_basis,
        }
        missing = [name for name, value in required.items() if value in (None, "")]
        if missing:
            raise BadRequestException(f"正式风险结论缺少必填确认信息：{', '.join(missing)}")
    latest = max((item.version_no for item in risk_case.assessments), default=0)
    payload = data.model_dump()
    payload["input_hash"] = hashlib.sha256(
        json.dumps(
            {
                "risk_case_id": risk_case.id,
                "solution_version_id": data.solution_version_id,
                "jurisdiction_code": data.jurisdiction_code,
                "preliminary_assessment": data.preliminary_assessment,
                "analysis_confirmation": data.analysis_confirmation,
                "discussion_conclusion": data.discussion_conclusion,
                "leadership_confirmation": data.leadership_confirmation,
                "decision_basis": data.decision_basis,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    if not is_draft and not payload.get("decision_at"):
        payload["decision_at"] = _now()
    if not is_draft and not payload.get("confirmed_at"):
        payload["confirmed_at"] = _now()
    assessment = RiskAssessmentVersion(
        risk_case_id=risk_case.id,
        version_no=latest + 1,
        **payload,
    )
    db.add(assessment)
    if not is_draft:
        risk_case.current_risk_level = data.risk_level
        risk_case.current_decision = data.decision
        risk_case.current_gate_impact = data.gate_impact
        risk_case.status = {
            "closed": "closed",
            "accepted": "accepted",
            "mitigate": "mitigation_required",
            "avoid": "mitigation_required",
            "continue_with_risk": "accepted",
        }.get(data.decision, "open")
    db.commit()
    return get_risk_case(db, risk_case_id)


def add_risk_review(db: Session, risk_case_id: int, data) -> RiskCase:
    risk_case = get_risk_case(db, risk_case_id)
    review = RiskReviewEvent(risk_case_id=risk_case.id, **data.model_dump())
    risk_case.next_review_condition = data.next_review_condition
    risk_case.next_review_at = data.next_review_at
    db.add(review)
    db.commit()
    return get_risk_case(db, risk_case_id)
