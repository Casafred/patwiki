"""统一的数据库审计时间工具。

SQLite 中的 DateTime 字段约定保存 UTC naive datetime；API 序列化后，
前端按 UTC 解读并转换到本机时区。专利事实日期不是审计时间，不使用本模块。
"""
from datetime import datetime, timezone


def utc_now_naive() -> datetime:
    """Return the current UTC time without tzinfo for legacy SQLite columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
