"""同族/引用关系解析与入库服务——P0-10 新增。

Excel 列 "同族专利号" / "引用专利" / "被引用专利" / "同族公开号" 中可能包含多种分隔符，
本服务负责解析这些列、创建/复用关系记录、为占位专利建立条目。
"""
import hashlib
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    Patent, PatentFamily, Citation,
)


# 同族/引用列的常见分隔符：分号、逗号、顿号、竖线、换行、Tab、连续空格（≥2）
# 竖线 | 是 incopat 等导出工具常见分隔符；连续空格用于应对无显式分隔符但用空格对齐的情况
SPLIT_PATTERN = re.compile(r"[;；,，、|\n\r\t]+|\s{2,}")

# 专利号格式校验：必须同时含字母和数字，长度 5-30，仅允许字母数字和连字符
_PATENT_NUM_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9\-]+$")

# 日期前缀乱码检测：8 位纯数字开头（如 20061102AU2005201606A1 = 日期+专利号合并）
# 正常专利号都以国家码开头（CN/US/EP/JP/KR/WO 等），不会以 8 位纯数字开头
_DATE_PREFIX_RE = re.compile(r"^\d{8}")


def _normalize_patent_number(num: str) -> Optional[str]:
    """清洗单个专利号：去括号、修剪首尾非字母数字字符、校验格式。

    返回 None 表示该字符串不是合法专利号，调用方应跳过。
    """
    if not num:
        return None
    num = num.strip()
    if not num:
        return None
    # 去除括号内容（如 CN115000123A(2023.05.01) → CN115000123A）
    num = re.sub(r"[（(][^)）]*[)）]", "", num).strip()
    if not num:
        return None
    # 修剪首尾非字母数字字符（如 " CN115000123A " 或 "|CN115000123A|"）
    num = re.sub(r"^[^A-Za-z0-9]+", "", num)
    num = re.sub(r"[^A-Za-z0-9]+$", "", num)
    if not num:
        return None
    # 长度校验：专利号通常 5-30 字符
    if len(num) < 5 or len(num) > 30:
        return None
    # 格式校验：必须同时含字母和数字
    if not _PATENT_NUM_RE.match(num):
        return None
    # 日期前缀乱码过滤：排除 20061102AU2005201606A1 这种日期+专利号合并的字符串
    if _DATE_PREFIX_RE.match(num):
        return None
    return num


def parse_patent_numbers(raw: str) -> list[str]:
    """把单元格里的多个专利号解析为列表。

    支持分号、逗号、顿号、竖线、换行、Tab、连续空格等分隔符；
    去除空白和括号内容（如公开日期）；过滤不合法的乱码字符串。
    """
    if not raw:
        return []
    if not isinstance(raw, str):
        raw = str(raw)
    parts = SPLIT_PATTERN.split(raw)
    result: list[str] = []
    for p in parts:
        normalized = _normalize_patent_number(p)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _find_or_create_patent_by_number(
    db: Session,
    number: str,
    database_id: Optional[int] = None,
) -> Optional[Patent]:
    """根据申请号或公开号找专利；找不到则创建占位专利。

    占位专利只有 application_number/publication_number + title="待补全"，
    后续导入或外部 API 补全时通过 merge_service 字段级合并。
    返回 None 表示号格式不合法，调用方应跳过。
    """
    # 二次校验号格式，防止外部直接调用传入乱码
    normalized = _normalize_patent_number(number)
    if not normalized:
        return None
    number = normalized

    # 优先按申请号找
    existing = db.query(Patent).filter(Patent.application_number == number).first()
    if existing:
        return existing
    # 再按公开号找
    existing = db.query(Patent).filter(Patent.publication_number == number).first()
    if existing:
        return existing

    # 创建占位专利
    placeholder = Patent(
        title="待补全",
        application_number=number if number.startswith(("CN", "US", "EP", "JP", "KR", "WO", "PCT")) else None,
        publication_number=number if not number.startswith(("CN", "US", "EP", "JP", "KR", "WO", "PCT")) else None,
        country=number[:2] if number[:2].isalpha() else "CN",
        database_id=database_id,
        notes="由同族/引用关系解析自动创建的占位专利",
    )
    db.add(placeholder)
    db.flush()
    return placeholder


def _get_or_create_family(
    db: Session,
    member_numbers: list[str],
) -> PatentFamily:
    """根据成员号列表的哈希找/创建 PatentFamily。"""
    sorted_numbers = sorted(set(member_numbers))
    family_id_str = "FAM_" + hashlib.md5("|".join(sorted_numbers).encode("utf-8")).hexdigest()[:12]
    existing = db.query(PatentFamily).filter(PatentFamily.family_id == family_id_str).first()
    if existing:
        return existing
    family = PatentFamily(
        family_id=family_id_str,
        family_type="simple",
        description=f"由同族号列表自动识别：{', '.join(sorted_numbers[:5])}{'...' if len(sorted_numbers) > 5 else ''}",
    )
    db.add(family)
    db.flush()
    return family


def process_family_members(
    db: Session,
    current_patent: Patent,
    family_numbers: list[str],
    database_id: Optional[int] = None,
) -> dict:
    """处理同族号列表：找/建 PatentFamily，把所有成员专利的 family_id 指向同一族。

    返回: {"family_id": int|None, "members_created": int, "members_linked": int}
    """
    if not family_numbers:
        return {"family_id": None, "members_created": 0, "members_linked": 0}

    # 包含当前专利号（若有）
    current_num = current_patent.application_number or current_patent.publication_number
    all_numbers = list(family_numbers)
    if current_num and current_num not in all_numbers:
        all_numbers.append(current_num)

    family = _get_or_create_family(db, all_numbers)

    members_created = 0
    members_linked = 0

    for num in family_numbers:
        num = num.strip()
        if not num:
            continue
        # 找/建成员专利（号格式不合法时返回 None，跳过）
        member = _find_or_create_patent_by_number(db, num, database_id)
        if member is None:
            continue
        if member.id is None:
            members_created += 1
        if member.family_id != family.id:
            member.family_id = family.id
            members_linked += 1

    # 当前专利也归入该族
    if current_patent.family_id != family.id:
        current_patent.family_id = family.id
        members_linked += 1

    db.flush()
    return {"family_id": family.id, "members_created": members_created, "members_linked": members_linked}


def process_citations(
    db: Session,
    current_patent: Patent,
    cited_numbers: list[str],
    database_id: Optional[int] = None,
) -> dict:
    """处理"引用专利"列：当前专利 → 引用列中的专利。

    返回: {"created": int, "links": int}
    """
    return _process_citation_direction(
        db, current_patent, cited_numbers,
        is_citing=True,  # 当前专利是 citing
        database_id=database_id,
    )


def process_citing_patents(
    db: Session,
    current_patent: Patent,
    citing_numbers: list[str],
    database_id: Optional[int] = None,
) -> dict:
    """处理"被引用专利"列：列中专利 → 引用当前专利。

    返回: {"created": int, "links": int}
    """
    return _process_citation_direction(
        db, current_patent, citing_numbers,
        is_citing=False,  # 当前专利是被 cited 的
        database_id=database_id,
    )


def _process_citation_direction(
    db: Session,
    current_patent: Patent,
    numbers: list[str],
    is_citing: bool,
    database_id: Optional[int] = None,
) -> dict:
    created = 0
    links = 0
    if not numbers:
        return {"created": created, "links": links}

    for num in numbers:
        num = num.strip()
        if not num:
            continue
        other = _find_or_create_patent_by_number(db, num, database_id)
        # 号格式不合法时跳过，不创建占位专利也不建关系
        if other is None:
            continue
        if other.id is None:
            created += 1

        # 建立引用关系
        if is_citing:
            citing_id = current_patent.id
            cited_id = other.id
        else:
            citing_id = other.id
            cited_id = current_patent.id

        # 避免重复
        existing_link = db.query(Citation).filter(
            Citation.citing_patent_id == citing_id,
            Citation.cited_patent_id == cited_id,
        ).first()
        if not existing_link:
            citation = Citation(
                citing_patent_id=citing_id,
                cited_patent_id=cited_id,
                citation_type="citation",
            )
            db.add(citation)
            links += 1

    db.flush()
    return {"created": created, "links": links}
