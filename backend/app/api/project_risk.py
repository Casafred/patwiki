"""Project solution versions and risk context APIs."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.schemas import (
    ProjectSolutionVersion,
    ProjectSolutionVersionCreate,
    ProjectSolutionVersionUpdate,
    RiskAssessment,
    RiskAssessmentCreate,
    RiskCase,
    RiskCaseCreate,
    RiskCaseUpdate,
    RiskReview,
    RiskReviewCreate,
    SolutionVersionConfirmRequest,
)
from app.services.project_risk_service import (
    add_risk_assessment,
    add_risk_review,
    confirm_solution_version,
    create_risk_case,
    create_solution_version,
    get_risk_case,
    get_solution_version,
    list_risk_cases,
    list_solution_versions,
    update_risk_case,
    update_solution_version,
)

router = APIRouter(tags=["project-risk"])


@router.get("/projects/{project_id}/solution-versions", response_model=list[ProjectSolutionVersion])
def list_project_solution_versions(
    project_id: int,
    database_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    return list_solution_versions(db, project_id, database_id)


@router.post("/projects/{project_id}/solution-versions", response_model=ProjectSolutionVersion)
def create_project_solution_version(
    project_id: int,
    request: ProjectSolutionVersionCreate,
    db: Session = Depends(get_db),
):
    return create_solution_version(db, project_id, request)


@router.get("/solution-versions/{solution_version_id}", response_model=ProjectSolutionVersion)
def get_project_solution_version(solution_version_id: int, db: Session = Depends(get_db)):
    return get_solution_version(db, solution_version_id)


@router.put("/solution-versions/{solution_version_id}", response_model=ProjectSolutionVersion)
def update_project_solution_version(
    solution_version_id: int,
    request: ProjectSolutionVersionUpdate,
    db: Session = Depends(get_db),
):
    return update_solution_version(db, solution_version_id, request)


@router.post("/solution-versions/{solution_version_id}/confirm", response_model=ProjectSolutionVersion)
def confirm_project_solution_version(
    solution_version_id: int,
    request: SolutionVersionConfirmRequest,
    db: Session = Depends(get_db),
):
    return confirm_solution_version(db, solution_version_id, request.confirmed_by)


@router.get("/risk-cases", response_model=list[RiskCase])
def list_cases(
    database_id: int = Query(...),
    patent_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    return list_risk_cases(db, database_id, patent_id, status)


@router.post("/risk-cases", response_model=RiskCase)
def create_case(request: RiskCaseCreate, db: Session = Depends(get_db)):
    return create_risk_case(db, request)


@router.get("/risk-cases/{risk_case_id}", response_model=RiskCase)
def get_case(risk_case_id: int, db: Session = Depends(get_db)):
    return get_risk_case(db, risk_case_id)


@router.put("/risk-cases/{risk_case_id}", response_model=RiskCase)
def update_case(risk_case_id: int, request: RiskCaseUpdate, db: Session = Depends(get_db)):
    return update_risk_case(db, risk_case_id, request)


@router.post("/risk-cases/{risk_case_id}/assessments", response_model=RiskCase)
def create_assessment(
    risk_case_id: int,
    request: RiskAssessmentCreate,
    db: Session = Depends(get_db),
):
    return add_risk_assessment(db, risk_case_id, request)


@router.post("/risk-cases/{risk_case_id}/reviews", response_model=RiskCase)
def create_review(
    risk_case_id: int,
    request: RiskReviewCreate,
    db: Session = Depends(get_db),
):
    return add_risk_review(db, risk_case_id, request)
