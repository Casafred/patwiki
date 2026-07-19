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


@router.get("/tasks")
def list_tasks(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """列出所有 AI 任务，按创建时间倒序"""
    q = db.query(AITask)
    if status:
        q = q.filter(AITask.status == status)
    tasks = q.order_by(AITask.id.desc()).limit(limit).all()
    return [
        {
            "id": t.id,
            "task_type": t.task_type,
            "field_key": t.field_key,
            "model_name": t.model_name,
            "status": t.status,
            "total_items": t.total_items,
            "processed_items": t.processed_items,
            "success_count": t.success_count,
            "failed_count": t.failed_count,
            "errors": t.errors,
            "started_at": t.started_at,
            "completed_at": t.completed_at,
            "created_at": t.created_at,
        }
        for t in tasks
    ]


@router.delete("/tasks/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    """删除任务记录（仅允许删除已完成/失败的任务）"""
    task = db.query(AITask).filter(AITask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status in ("pending", "processing", "running"):
        raise HTTPException(status_code=400, detail="运行中的任务不能删除")
    db.delete(task)
    db.commit()
    return {"success": True}


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
