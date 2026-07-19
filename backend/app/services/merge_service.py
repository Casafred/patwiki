"""Wiki 式字段合并服务——P0-10 新增。

核心原则：导入即增补，不覆盖。
- 著录类字段：新值非空就覆盖（以最新 Excel 为准）
- 标注类字段（has_risk/risk_level/notes 等）：仅在新值非空时覆盖，避免冲掉人工标注
- 自定义字段：字典级合并，仅覆盖非空新值
"""
from typing import Any

from app.models import Patent


# 标注类字段：人工录入的业务标注，导入时不允许被空值冲掉
ANNOTATION_FIELDS = {
    "category", "subcategory",
    "technical_problem", "technical_effect", "technical_solution",
    "has_risk", "risk_level", "risk_description",
    "module", "application_status",
    "scope_description", "notes",
}


def _is_empty(value: Any) -> bool:
    """判断值是否为空（None / 空字符串 / 空列表 / 空字典）。"""
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    return False


def merge_patent_data(existing: Patent, new_data: dict) -> dict:
    """计算 Wiki 式合并后的字段更新字典。

    参数:
        existing: 已存在的 Patent 实例
        new_data: 本次导入解析出的字段字典（含 custom_fields 子字典）

    返回:
        合并后的更新字典，可直接传给 PatentService.update_patent
    """
    merged: dict[str, Any] = {}

    for field, new_value in new_data.items():
        if field == "custom_fields":
            continue

        if _is_empty(new_value):
            # 新值为空：标注类字段保留原值（不写入 merged），著录类也跳过
            continue

        # 非空新值：覆盖（无论标注类还是著录类都更新）
        merged[field] = new_value

    # 自定义字段：字典级合并，保留已有值，仅覆盖非空新值
    new_custom = new_data.get("custom_fields") or {}
    if new_custom:
        existing_custom = dict(existing.custom_fields or {})
        for k, v in new_custom.items():
            if not _is_empty(v):
                existing_custom[k] = v
        merged["custom_fields"] = existing_custom

    return merged


def diff_patent_data(existing: Patent, new_data: dict) -> dict:
    """仅返回与现有值不同的字段（用于冲突检测/审计日志）。"""
    diff: dict[str, Any] = {}
    for field, new_value in new_data.items():
        if field == "custom_fields":
            continue
        if _is_empty(new_value):
            continue
        old_value = getattr(existing, field, None)
        if old_value != new_value:
            diff[field] = {"old": old_value, "new": new_value}
    return diff
