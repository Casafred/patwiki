from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional
import json
from datetime import datetime

from app.database import get_db, SessionLocal
from app.schemas.schemas import AIProcessRequest, AITaskResponse
from app.models import AITask, Patent, AIFieldValue, CustomField
from app.config import settings

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/process", response_model=AITaskResponse)
async def start_ai_process(
    req: AIProcessRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    field = db.query(CustomField).filter(CustomField.key == req.field_key).first()
    if not field:
        raise HTTPException(status_code=404, detail=f"AI field '{req.field_key}' not found")

    task = AITask(
        task_type="field_calculation",
        field_key=req.field_key,
        model_name=req.model or settings.LLM_MODEL,
        total_items=len(req.patent_ids),
        status="pending",
        config={"patent_ids": req.patent_ids, "force": req.force_recalculate},
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    def run_ai_task():
        db = SessionLocal()
        try:
            from app.ai.fields.engine import AIFieldEngine
            engine = AIFieldEngine(db)
            engine.process_batch(task.id, req.patent_ids, req.field_key, req.force_recalculate)
        finally:
            db.close()

    background_tasks.add_task(run_ai_task)

    return task


@router.get("/tasks/{task_id}", response_model=AITaskResponse)
def get_task_status(task_id: int, db: Session = Depends(get_db)):
    task = db.query(AITask).filter(AITask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/fields")
def list_ai_fields(db: Session = Depends(get_db)):
    fields = db.query(CustomField).filter(
        CustomField.field_type == "ai_field",
        CustomField.is_active == True,
    ).all()
    return [
        {
            "key": f.key,
            "name": f.name,
            "description": f.description,
            "ai_config": f.ai_config,
        }
        for f in fields
    ]
