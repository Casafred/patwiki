"""
统计分析模块
- 列统计：对任意字段做去重值计数
- AGENTAI 看板：基层代码统计 + AI 多维分析（两阶段）
- 统计结果转标签体系：把某列的去重值批量转为标签
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Optional, Any
from pydantic import BaseModel
from datetime import datetime
import json

from app.database import get_db, SessionLocal
from app.models import (
    Patent, CustomField, Tag, TagGroup, AITask,
)
from app.services.field_registry import SYSTEM_FIELD_KEYS
from app.services.patent_service import PatentService
from app.config import settings

router = APIRouter(tags=["analytics"])


# ============================================================
# 工具：从 Patent 上取字段值，支持系统字段 / custom_fields.xxx / ai_fields.xxx
# ============================================================
def _resolve_field_column(key: str):
    """返回 (SQL表达式, is_json_extract, json_path) 三元组"""
    if key.startswith("custom_fields."):
        ck = key[len("custom_fields."):]
        return func.json_extract(Patent.custom_fields, f'$.{ck}'), True, f'$.{ck}'
    if key.startswith("ai_fields."):
        ak = key[len("ai_fields."):]
        return func.json_extract(Patent.ai_fields, f'$.{ak}'), True, f'$.{ak}'
    # 系统字段
    if hasattr(Patent, key):
        return getattr(Patent, key), False, None
    # 默认当作 custom_fields.xxx
    return func.json_extract(Patent.custom_fields, f'$.{key}'), True, f'$.{key}'


# ============================================================
# 1. 列统计接口：返回去重值列表 + 计数 + 占比
# ============================================================
class ColumnStatsRequest(BaseModel):
    field_key: str
    database_id: Optional[int] = None
    product_id: Optional[int] = None
    project_id: Optional[int] = None
    tag_id: Optional[int] = None
    legal_status: Optional[str] = None
    category: Optional[str] = None
    risk_level: Optional[str] = None
    patent_type: Optional[str] = None
    country: Optional[str] = None
    filters: Optional[dict[str, Any]] = None
    top_n: int = 100


@router.post("/analytics/column-stats")
def column_stats(req: ColumnStatsRequest, db: Session = Depends(get_db)):
    """对任意字段做去重值统计，返回 [{value, count, percentage}]"""
    col, is_json, json_path = _resolve_field_column(req.field_key)

    # 构建基础筛选 query（复用 list_patents 的筛选逻辑，但不分页）
    query = db.query(col.label("v"), func.count(Patent.id).label("c"))
    query = _apply_common_filters(query, req)

    # 分组统计
    rows = query.group_by("v").order_by(func.count(Patent.id).desc()).limit(req.top_n).all()

    total = sum(r[1] for r in rows)
    result = []
    for r in rows:
        val = r[0]
        cnt = int(r[1])
        # 把 None / "" 显示为 "(空)"
        if val is None or (isinstance(val, str) and val.strip() == ""):
            display = "(空)"
        else:
            display = str(val)
        result.append({
            "value": display,
            "raw_value": val if val is not None else "",
            "count": cnt,
            "percentage": round(cnt / total * 100, 2) if total else 0,
        })
    return {
        "field_key": req.field_key,
        "total_distinct": len(rows),
        "total_rows": total,
        "items": result,
    }


def _apply_common_filters(query, req):
    """通用筛选条件应用"""
    if getattr(req, "database_id", None):
        query = query.filter(Patent.database_id == req.database_id)
    if getattr(req, "product_id", None):
        query = query.filter(Patent.product_id == req.product_id)
    if getattr(req, "project_id", None):
        from app.models import patent_project
        query = query.join(patent_project).filter(patent_project.c.project_id == req.project_id)
    if getattr(req, "tag_id", None):
        from app.models import patent_tag
        query = query.join(patent_tag).filter(patent_tag.c.tag_id == req.tag_id)
    if getattr(req, "legal_status", None):
        query = query.filter(Patent.legal_status == req.legal_status)
    if getattr(req, "category", None):
        query = query.filter(Patent.category == req.category)
    if getattr(req, "risk_level", None):
        query = query.filter(Patent.risk_level == req.risk_level)
    if getattr(req, "patent_type", None):
        query = query.filter(Patent.patent_type == req.patent_type)
    if getattr(req, "country", None):
        query = query.filter(Patent.country == req.country)
    if getattr(req, "filters", None):
        for key, fv in req.filters.items():
            if not fv:
                continue
            col, _, _ = _resolve_field_column(key)
            if isinstance(fv, dict):
                if fv.get("contains"):
                    query = query.filter(col.cast(str).ilike(f"%{fv['contains']}%"))
                elif fv.get("eq") is not None:
                    query = query.filter(col == fv["eq"])
            else:
                query = query.filter(col.cast(str).ilike(f"%{fv}%"))
    return query


# ============================================================
# 2. 统计结果转标签体系
# ============================================================
class StatsToTagsRequest(BaseModel):
    field_key: str
    group_name: str = "自动分类"
    group_color: str = "#3b82f6"
    tag_color: str = "#60a5fa"
    only_non_empty: bool = True
    auto_apply_to_patents: bool = True  # 是否自动给原专利打上对应标签
    database_id: Optional[int] = None
    product_id: Optional[int] = None
    project_id: Optional[int] = None


@router.post("/analytics/stats-to-tags")
def stats_to_tags(req: StatsToTagsRequest, db: Session = Depends(get_db)):
    """把某列的去重值批量转为标签，可选自动给原专利打标"""
    # 1. 获取或创建标签组
    group = db.query(TagGroup).filter(TagGroup.name == req.group_name).first()
    if not group:
        group = TagGroup(name=req.group_name, color=req.group_color)
        db.add(group)
        db.commit()
        db.refresh(group)

    # 2. 统计该列所有去重值
    col, _, _ = _resolve_field_column(req.field_key)
    query = db.query(col.label("v"), func.count(Patent.id).label("c"))
    query = _apply_common_filters(query, req)
    rows = query.group_by("v").all()

    created_tags = []
    applied_count = 0

    for r in rows:
        val = r[0]
        if val is None or (isinstance(val, str) and val.strip() == ""):
            if req.only_non_empty:
                continue
            tag_name = "(空)"
        else:
            tag_name = str(val).strip()
            if not tag_name:
                continue

        # 3. 获取或创建标签
        tag = db.query(Tag).filter(Tag.name == tag_name, Tag.group_id == group.id).first()
        if not tag:
            tag = Tag(name=tag_name, group_id=group.id, color=req.tag_color)
            db.add(tag)
            db.commit()
            db.refresh(tag)

        created_tags.append({"id": tag.id, "name": tag_name, "count": int(r[1])})

        # 4. 自动给原专利打标
        if req.auto_apply_to_patents:
            patents_q = db.query(Patent)
            patents_q = _apply_common_filters(patents_q, req)
            patents_with_val = patents_q.filter(col == val).all()
            for p in patents_with_val:
                if tag not in p.tags:
                    p.tags.append(tag)
                    applied_count += 1
            db.commit()

    return {
        "group": {"id": group.id, "name": group.name},
        "tags": created_tags,
        "total_tags": len(created_tags),
        "applied_count": applied_count,
    }


# ============================================================
# 3. AGENTAI 看板：基层代码统计 + AI 多维分析（两阶段）
# ============================================================
class AgentAnalysisRequest(BaseModel):
    requirement: str  # 用户的自然语言分析需求
    database_id: Optional[int] = None
    product_id: Optional[int] = None
    project_id: Optional[int] = None
    tag_id: Optional[int] = None
    filters: Optional[dict[str, Any]] = None
    dimensions: Optional[list[str]] = None  # 指定参与统计的维度字段
    top_n: int = 20


def _do_base_statistics(db: Session, req: AgentAnalysisRequest) -> dict:
    """
    第一阶段：基层代码统计
    不调用 AI，纯 SQL/Python 聚合，输出结构化统计数据
    """
    # 默认统计维度
    default_dims = [
        "legal_status", "patent_type", "country", "category",
        "risk_level", "applicant", "inventor", "ipc_main",
    ]
    dims = req.dimensions or default_dims

    stats = {}
    # 总数
    base_q = db.query(Patent.id)
    base_q = _apply_common_filters(base_q, req)
    total = base_q.count()
    stats["total"] = total

    if total == 0:
        return {"total": 0, "dimensions": {}, "filing_trend": [], "summary": "无数据"}

    # 各维度分组统计
    dim_results = {}
    for dim in dims:
        col, _, _ = _resolve_field_column(dim)
        q = db.query(col.label("v"), func.count(Patent.id).label("c"))
        q = _apply_common_filters(q, req)
        rows = q.group_by("v").order_by(func.count(Patent.id).desc()).limit(req.top_n).all()
        items = []
        for r in rows:
            v = r[0]
            items.append({
                "value": str(v) if v is not None else "(空)",
                "count": int(r[1]),
                "percentage": round(int(r[1]) / total * 100, 2) if total else 0,
            })
        dim_results[dim] = items

    stats["dimensions"] = dim_results

    # 申请年份趋势
    try:
        trend_q = db.query(
            func.strftime("%Y", Patent.filing_date).label("year"),
            func.count(Patent.id).label("c"),
        ).filter(Patent.filing_date.isnot(None))
        trend_q = _apply_common_filters(trend_q, req)
        trend_rows = trend_q.group_by("year").order_by("year").all()
        stats["filing_trend"] = [
            {"year": r[0], "count": int(r[1])} for r in trend_rows if r[0]
        ]
    except Exception:
        stats["filing_trend"] = []

    # 字段概要
    parts = [f"共 {total} 条专利。"]
    if dim_results.get('legal_status'):
        ls = ", ".join(f"{d['value']}({d['count']})" for d in dim_results['legal_status'][:5])
        parts.append(f" 法律状态分布: {ls}。")
    if dim_results.get('applicant'):
        ap = ", ".join(f"{d['value']}({d['count']})" for d in dim_results['applicant'][:5])
        parts.append(f" 申请人TOP5: {ap}。")
    stats["summary"] = "".join(parts)

    return stats


def _do_ai_analysis(base_stats: dict, requirement: str) -> dict:
    """
    第二阶段：AI 多维分析
    把基层统计数据 + 用户需求交给 LLM，生成结构化分析报告
    """
    # 构造给 AI 的输入（不是原始数据，是统计摘要）
    stats_brief = json.dumps(base_stats, ensure_ascii=False, default=str)

    prompt = f"""你是专利数据分析师。请根据以下统计数据和用户需求，生成结构化的多维分析报告。

【用户需求】
{requirement}

【统计数据】（已聚合，非原始数据）
{stats_brief}

【输出要求】
请用 JSON 格式输出，包含以下字段：
{{
  "overview": "总体概述（2-3句话）",
  "key_findings": ["关键发现1", "关键发现2", "关键发现3"],
  "dimension_analysis": {{
    "维度名": "该维度的分析结论"
  }},
  "anomalies": ["异常点或值得关注的模式1", "异常点2"],
  "recommendations": ["建议1", "建议2", "建议3"],
  "risk_warnings": ["风险提示1", "风险提示2"]
}}

只输出 JSON，不要多余的解释。"""

    try:
        from app.ai.fields.engine import AIFieldEngine
        engine = AIFieldEngine(SessionLocal())
        llm = engine._get_llm()
        if llm is None:
            return {
                "overview": "AI 分析未启用（未配置 LLM API）",
                "key_findings": [base_stats.get("summary", "")],
                "dimension_analysis": {},
                "anomalies": [],
                "recommendations": ["请在设置页配置 LLM API 后使用 AI 分析功能"],
                "risk_warnings": [],
            }
        # 调用 LLM
        if hasattr(llm, "invoke"):
            resp = llm.invoke(prompt)
            content = resp.content if hasattr(resp, "content") else str(resp)
        else:
            resp = llm.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            content = resp.choices[0].message.content

        # 解析 JSON
        # 移除可能的 ```json 包裹
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        return json.loads(content)
    except json.JSONDecodeError:
        return {
            "overview": content[:500] if 'content' in dir() else "AI 返回格式异常",
            "key_findings": [],
            "dimension_analysis": {},
            "anomalies": [],
            "recommendations": [],
            "risk_warnings": [],
        }
    except Exception as e:
        return {
            "overview": f"AI 分析失败: {str(e)}",
            "key_findings": [base_stats.get("summary", "")],
            "dimension_analysis": {},
            "anomalies": [],
            "recommendations": ["请检查 LLM API 配置"],
            "risk_warnings": [],
        }


@router.post("/analytics/agent-analysis")
def agent_analysis(req: AgentAnalysisRequest, db: Session = Depends(get_db)):
    """AGENTAI 看板：两阶段分析（基层统计 + AI 分析）"""
    # 第一阶段：基层代码统计
    base_stats = _do_base_statistics(db, req)

    # 第二阶段：AI 多维分析
    ai_result = _do_ai_analysis(base_stats, req.requirement)

    return {
        "requirement": req.requirement,
        "base_stats": base_stats,
        "ai_analysis": ai_result,
        "created_at": datetime.now().isoformat(),
    }


# ============================================================
# 4. 多维交叉统计（用于看板快速生成）
# ============================================================
class CrossTabRequest(BaseModel):
    row_field: str
    col_field: str
    value_field: Optional[str] = None  # 值字段，默认计数
    agg_func: str = "count"  # count / sum / avg
    database_id: Optional[int] = None
    product_id: Optional[int] = None
    project_id: Optional[int] = None
    filters: Optional[dict[str, Any]] = None
    top_n: int = 20


@router.post("/analytics/crosstab")
def cross_tab(req: CrossTabRequest, db: Session = Depends(get_db)):
    """交叉统计表（行x列）"""
    row_col, _, _ = _resolve_field_column(req.row_field)
    col_col, _, _ = _resolve_field_column(req.col_field)

    q = db.query(
        row_col.label("r"),
        col_col.label("c"),
        func.count(Patent.id).label("v"),
    )
    q = _apply_common_filters(q, req)
    rows = q.group_by("r", "c").all()

    # 构建交叉表
    row_values = sorted(set(str(r[0]) if r[0] is not None else "(空)" for r in rows))
    col_values = sorted(set(str(r[1]) if r[1] is not None else "(空)" for r in rows))

    matrix = {rv: {cv: 0 for cv in col_values} for rv in row_values}
    for r in rows:
        rv = str(r[0]) if r[0] is not None else "(空)"
        cv = str(r[1]) if r[1] is not None else "(空)"
        matrix[rv][cv] = int(r[2])

    return {
        "row_field": req.row_field,
        "col_field": req.col_field,
        "row_values": row_values[:req.top_n],
        "col_values": col_values[:req.top_n],
        "matrix": {rv: matrix[rv] for rv in row_values[:req.top_n]},
    }
