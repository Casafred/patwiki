from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional
import json
import hashlib
from datetime import datetime

from app.database import get_db, SessionLocal
from app.schemas.schemas import AIProcessRequest, AITaskResponse, QuickAnalyzeRequest
from app.models import AITask, Patent, AIFieldValue, CustomField
from app.models.enums import CustomFieldType
from app.config import settings
from app.core.exceptions import BadRequestException, NotFoundException

router = APIRouter(prefix="/ai", tags=["ai"])


def _task_errors(task: AITask) -> list[dict] | None:
    """Normalize legacy task rows so every API response has array-shaped errors."""
    if task.errors is None:
        return None
    if isinstance(task.errors, list):
        return task.errors
    if isinstance(task.errors, dict):
        return [task.errors]
    return [{"error": str(task.errors)}]


def _task_payload(task: AITask) -> dict:
    return {
        "id": task.id,
        "task_type": task.task_type,
        "field_key": task.field_key,
        "model_name": task.model_name,
        "status": task.status,
        "total_items": task.total_items,
        "processed_items": task.processed_items,
        "success_count": task.success_count,
        "failed_count": task.failed_count,
        "errors": _task_errors(task),
        "request_content": task.request_content,
        "response_content": task.response_content,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
        "created_at": task.created_at,
    }


@router.post("/process", response_model=AITaskResponse)
async def start_ai_process(
    req: AIProcessRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
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

    field = db.query(CustomField).filter(CustomField.key == req.field_key).first()
    if not field:
        task.status = "failed"
        task.processed_items = task.total_items
        task.failed_count = task.total_items
        task.errors = [{"stage": "prepare", "error": f"AI field '{req.field_key}' not found"}]
        task.completed_at = datetime.now()
        db.commit()
        db.refresh(task)
        return task

    def run_ai_task():
        db = SessionLocal()
        try:
            from app.ai.fields.engine import AIFieldEngine
            engine = AIFieldEngine(db)
            engine.process_batch(task.id, req.patent_ids, req.field_key, req.force_recalculate)
        except Exception as exc:
            db.rollback()
            task_row = db.query(AITask).filter(AITask.id == task.id).first()
            if task_row:
                task_row.status = "failed"
                task_row.processed_items = max(task_row.processed_items or 0, 0)
                task_row.failed_count = max(task_row.failed_count or 0, task_row.total_items or 0)
                task_row.errors = [
                    *(_task_errors(task_row) or []),
                    {"stage": "background", "error": str(exc)},
                ]
                task_row.completed_at = datetime.now()
                db.commit()
        finally:
            db.close()

    background_tasks.add_task(run_ai_task)

    return task


@router.get("/tasks/{task_id}", response_model=AITaskResponse)
def get_task_status(task_id: int, db: Session = Depends(get_db)):
    task = db.query(AITask).filter(AITask.id == task_id).first()
    if not task:
        raise NotFoundException("Task not found")
    return _task_payload(task)


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
            "errors": _task_errors(t),
            # P0-15：返回请求/返回内容样本，便于审计与调试
            "request_content": t.request_content,
            "response_content": t.response_content,
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
        raise NotFoundException("Task not found")
    if task.status in ("pending", "processing", "running"):
        raise BadRequestException("运行中的任务不能删除")
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


@router.post("/quick-analyze", response_model=AITaskResponse)
async def quick_analyze(
    req: QuickAnalyzeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """AI 快速分析：用户自定义输入列、提示词、抽取目标（已有或新建字段）。

    流程：
    1. 为每个"新建字段"的抽取目标创建 CustomField 记录
    2. 创建 AITask，后台批量执行
    3. 每条专利：构建 prompt → 调用 LLM → 解析 JSON → 写入目标字段
    """
    if not req.patent_ids:
        raise BadRequestException("请至少选择一条专利")
    if not req.prompt.strip():
        raise BadRequestException("请填写分析提示词")
    if not req.extractions:
        raise BadRequestException("请至少配置一个抽取目标")

    # 任务先落库。字段创建、配置校验、后台执行的任何失败都必须有任务记录。
    from app.services.llm_service import load_llm_config
    try:
        runtime_config = load_llm_config()
        model_name = runtime_config.model
    except Exception:
        model_name = settings.LLM_MODEL

    task = AITask(
        task_type="quick_analyze",
        field_key=None,
        model_name=model_name,
        total_items=len(req.patent_ids),
        status="pending",
        config={
            "patent_ids": req.patent_ids,
            "input_fields": req.input_fields,
            "prompt": req.prompt,
            "extractions": [],
        },
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    extraction_targets = []
    try:
        for ext in req.extractions:
            if not ext.name.strip():
                raise ValueError("抽取目标名称不能为空")
            if ext.target_field_key:
                # 快速抽取只允许写入已注册的自定义字段；系统字段的正式值
                # 需要人工确认，避免 AI 绕过字段类型和来源治理。
                field = db.query(CustomField).filter(
                    CustomField.key == ext.target_field_key,
                    CustomField.is_active == True,
                ).first()
                if not field:
                    raise ValueError(f"目标字段不存在或已停用：{ext.target_field_key}")
                if field.field_type in (
                    CustomFieldType.FORMULA,
                    CustomFieldType.ATTACHMENT,
                    CustomFieldType.LINK,
                    CustomFieldType.LOOKUP,
                    CustomFieldType.ROLLUP,
                ):
                    raise ValueError(f"目标字段不支持 AI 草稿写入：{field.name}")
                field_key = ext.target_field_key
            elif ext.new_field_name and ext.new_field_name.strip():
                field_type_str = ext.new_field_type or "text"
                try:
                    field_type = CustomFieldType(field_type_str)
                except ValueError:
                    field_type = CustomFieldType.TEXT
                seed = hashlib.sha1(ext.new_field_name.strip().encode("utf-8")).hexdigest()[:12]
                field_key = f"cf_ai_{seed}"
                suffix = 2
                while db.query(CustomField).filter(CustomField.key == field_key).first():
                    field_key = f"cf_ai_{seed}_{suffix}"
                    suffix += 1
                new_field = CustomField(
                    key=field_key,
                    name=ext.new_field_name.strip(),
                    field_type=field_type,
                    is_active=True,
                    sort_order=db.query(CustomField).count(),
                )
                db.add(new_field)
                db.flush()
            else:
                raise ValueError("每个抽取目标必须选择已有字段或填写新字段名称")

            extraction_targets.append({
                "name": ext.name.strip(),
                "target_field_key": field_key,
                "new_field_name": ext.new_field_name,
                "new_field_type": ext.new_field_type,
            })

        if not extraction_targets:
            raise ValueError("没有有效的抽取目标")
        task.config = {
            **(task.config or {}),
            "extractions": extraction_targets,
        }
        db.commit()
    except Exception as exc:
        db.rollback()
        task = db.query(AITask).filter(AITask.id == task.id).first()
        task.status = "failed"
        task.failed_count = task.total_items
        task.errors = [{"stage": "prepare", "error": str(exc)}]
        task.completed_at = datetime.now()
        db.commit()
        db.refresh(task)
        return task

    def run_quick_analyze():
        db = SessionLocal()
        try:
            from app.ai.fields.engine import AIFieldEngine
            engine = AIFieldEngine(db)
            engine.quick_analyze_batch(
                task.id, req.patent_ids, req.input_fields,
                req.prompt, extraction_targets,
            )
        except Exception as exc:
            db.rollback()
            task_row = db.query(AITask).filter(AITask.id == task.id).first()
            if task_row:
                task_row.status = "failed"
                task_row.errors = [
                    *(_task_errors(task_row) or []),
                    {"stage": "background", "error": str(exc)},
                ]
                task_row.completed_at = datetime.now()
                task_row.failed_count = max(task_row.failed_count or 0, task_row.total_items or 0)
                db.commit()
        finally:
            db.close()

    background_tasks.add_task(run_quick_analyze)
    return task
