"""Dashboard card validation and lightweight patent aggregations."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import Dashboard, Patent, PatentView
from app.services.view_service import ViewService


class DashboardService:
    CARD_TYPES = {"metric", "bar", "pie", "line", "progress", "table"}
    AGGREGATIONS = {"count", "sum", "avg", "min", "max"}

    @classmethod
    def normalize_card(cls, raw: dict[str, Any], index: int = 0) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise ValueError("仪表盘卡片必须是对象")
        card_type = str(raw.get("type", "metric"))
        if card_type not in cls.CARD_TYPES:
            raise ValueError(f"不支持的仪表盘卡片类型：{card_type}")
        title = str(raw.get("title") or "未命名卡片").strip()
        config = raw.get("config") or {}
        if not isinstance(config, dict):
            raise ValueError("仪表盘卡片 config 必须是对象")
        aggregation = str(config.get("aggregation", "count"))
        if aggregation not in cls.AGGREGATIONS:
            raise ValueError(f"不支持的聚合方式：{aggregation}")
        position = raw.get("position") or {}
        if not isinstance(position, dict):
            raise ValueError("仪表盘卡片 position 必须是对象")
        normalized_position = {
            "x": max(0, int(position.get("x", (index % 3) * 4))),
            "y": max(0, int(position.get("y", (index // 3) * 3))),
            "w": min(12, max(2, int(position.get("w", 4)))),
            "h": min(8, max(1, int(position.get("h", 2)))),
        }
        return {
            "id": str(raw.get("id") or f"card_{uuid4().hex[:10]}"),
            "type": card_type,
            "title": title,
            "config": {**config, "aggregation": aggregation},
            "position": normalized_position,
        }

    @classmethod
    def normalize_layout(cls, layout: Any) -> list[dict[str, Any]]:
        if layout in (None, []):
            return []
        if not isinstance(layout, list) or len(layout) > 50:
            raise ValueError("仪表盘最多配置 50 个卡片")
        return [cls.normalize_card(card, index) for index, card in enumerate(layout)]

    @staticmethod
    def _value(patent: Patent, field: str) -> Any:
        if field.startswith("custom_fields."):
            return (patent.custom_fields or {}).get(field[len("custom_fields."):])
        if field.startswith("ai_fields."):
            return (patent.ai_fields or {}).get(field[len("ai_fields."):])
        if hasattr(patent, field):
            value = getattr(patent, field)
            return value.value if hasattr(value, "value") else value
        return (patent.custom_fields or {}).get(field)

    @classmethod
    def _numeric_values(cls, patents: list[Patent], field: str) -> list[float]:
        values: list[float] = []
        for patent in patents:
            value = cls._value(patent, field)
            try:
                values.append(float(value))
            except (TypeError, ValueError):
                continue
        return values

    @classmethod
    def _aggregate(cls, patents: list[Patent], field: str, aggregation: str) -> float | int:
        if aggregation == "count":
            return len([patent for patent in patents if field == "id" or cls._value(patent, field) is not None])
        values = cls._numeric_values(patents, field)
        if not values:
            return 0
        if aggregation == "sum":
            return round(sum(values), 2)
        if aggregation == "avg":
            return round(sum(values) / len(values), 2)
        if aggregation == "min":
            return min(values)
        return max(values)

    @classmethod
    def _grouped(cls, patents: list[Patent], field: str) -> list[dict[str, Any]]:
        counter: Counter[str] = Counter()
        for patent in patents:
            value = cls._value(patent, field)
            if value is None or value == "":
                label = "未设置"
            elif isinstance(value, list):
                label = "、".join(str(item) for item in value) or "未设置"
            else:
                label = str(value)
            counter[label] += 1
        return [{"label": label, "value": count} for label, count in counter.most_common(20)]

    @classmethod
    def _card_data(cls, patents: list[Patent], card: dict[str, Any]) -> dict[str, Any]:
        card_type = card["type"]
        config = card["config"]
        field = str(config.get("field") or "id")
        aggregation = config.get("aggregation", "count")
        if card_type == "metric":
            return {"value": cls._aggregate(patents, field, aggregation)}
        if card_type in {"bar", "pie"}:
            group_field = str(config.get("group_by") or field)
            return {"items": cls._grouped(patents, group_field)}
        if card_type == "table":
            items = cls._grouped(patents, field)
            return {"items": items[:max(1, min(50, int(config.get("limit", 10))))]}
        if card_type == "progress":
            expected = config.get("value", config.get("target_value", "granted"))
            current = sum(1 for patent in patents if str(cls._value(patent, field)) == str(expected))
            total = len(patents)
            return {"current": current, "total": total, "percentage": round(current / total * 100, 1) if total else 0}
        date_field = str(config.get("date_field") or "filing_date")
        interval = str(config.get("interval", "year"))
        counter: Counter[str] = Counter()
        for patent in patents:
            value = cls._value(patent, date_field)
            if not value:
                continue
            label = str(value)[:7] if interval == "month" else str(value)[:4]
            counter[label] += 1
        ordered = sorted(counter.items())
        return {"labels": [item[0] for item in ordered], "values": [item[1] for item in ordered]}

    @classmethod
    def get_data(cls, db: Session, dashboard: Dashboard, view_id: Optional[int] = None) -> dict[str, Any]:
        patents: list[Patent]
        if view_id is not None:
            view = db.query(PatentView).filter(
                PatentView.id == view_id,
                PatentView.database_id == dashboard.database_id,
            ).first()
            if not view:
                raise ValueError("视图不属于当前仪表盘所在的库")
            patents, _ = ViewService.list_view_patents(db, view, page=1, page_size=1000)
        else:
            patents = db.query(Patent).filter(Patent.database_id == dashboard.database_id).all()
        cards = cls.normalize_layout(dashboard.layout or [])
        return {
            "dashboard_id": dashboard.id,
            "database_id": dashboard.database_id,
            "view_id": view_id,
            "total": len(patents),
            "cards": [
                {**card, "data": cls._card_data(patents, card)}
                for card in cards
            ],
        }
