"""Hierarchical classifications share the existing patent-tag association."""
from sqlalchemy import and_, or_, exists
from app.models import Tag, TagGroup, Product, Patent, PatentHistory, CrossTableLink
from app.core.exceptions import BadRequestException, NotFoundException


def ensure_product_tags(db):
    group = db.query(TagGroup).filter_by(kind="product").first()
    if not group:
        group = db.query(TagGroup).filter_by(name="产品分类").first()
        if not group:
            group = TagGroup(name="产品分类", kind="product", color="#0f766e")
            db.add(group)
        group.kind = "product"
        db.flush()
    for product in db.query(Product).all():
        tag = db.query(Tag).filter_by(group_id=group.id, product_id=product.id).first()
        if not tag:
            # Only migrate ungrouped exact product names; category text is ambiguous.
            tag = db.query(Tag).filter_by(group_id=None, name=product.name).first()
            tag = tag or db.query(Tag).filter_by(group_id=group.id, name=product.name, product_id=None).first()
            if not tag:
                name = product.name[:100]
                if db.query(Tag).filter_by(group_id=group.id, name=name).first():
                    name = f"{product.name[:80]} ({product.id})"
                tag = Tag(name=name, group_id=group.id, color="#0f766e")
                db.add(tag)
            tag.group_id, tag.product_id = group.id, product.id
        # Preserve existing classifications when a product is renamed.
        duplicate = db.query(Tag).filter(Tag.group_id == group.id, Tag.name == product.name, Tag.id != tag.id).first()
        if not duplicate:
            tag.name = product.name[:100]
    db.flush()
    return group


def sync_product_tags(db, patent, *, from_tags=False):
    if from_tags:
        products = sorted({tag.product_id for tag in patent.tags if tag.product_id})
        if patent.product_id not in products:
            patent.product_id = products[0] if products else None
        return
    group = ensure_product_tags(db)
    tags = [tag for tag in patent.tags if not tag.product_id or tag.group_id != group.id]
    if patent.product_id:
        tag = db.query(Tag).filter_by(group_id=group.id, product_id=patent.product_id).first()
        if not tag:
            raise BadRequestException("关联产品不存在")
        if tag not in tags:
            tags.append(tag)
    patent.tags = tags


def product_predicate(product_id):
    return or_(
        Patent.product_id == product_id,
        Patent.tags.any(Tag.product_id == product_id),
        exists().where(and_(CrossTableLink.source_table == "patents",
                            CrossTableLink.source_record_id == Patent.id,
                            CrossTableLink.target_table == "products",
                            CrossTableLink.target_record_id == product_id)),
    )


def migrate_ungrouped_tags(db):
    tags = db.query(Tag).filter(Tag.group_id.is_(None)).all()
    if not tags:
        return
    group = db.query(TagGroup).filter_by(name="未分组标签").first()
    if not group:
        group = TagGroup(name="未分组标签")
        db.add(group)
        db.flush()
    for tag in tags:
        existing = db.query(Tag).filter_by(group_id=group.id, name=tag.name).first()
        if existing:
            for patent in list(tag.patents):
                if existing not in patent.tags:
                    patent.tags.append(existing)
                patent.tags.remove(tag)
            # Keep the original ID available to integrations without exposing duplicate names.
            tag.name = f"{tag.name[:80]} ({tag.id})"
        tag.group_id = group.id
        db.flush()


def validate_tag(db, values, tag_id=None):
    name = str(values.get("name") or "").strip()
    if not name or len(name) > 100:
        raise BadRequestException("标签名称须为 1 至 100 个字符")
    values["name"] = name
    group_id, parent_id = values.get("group_id"), values.get("parent_id")
    group = db.get(TagGroup, group_id) if group_id else None
    if group_id and not group:
        raise BadRequestException("分类系统不存在")
    if values.get("product_id"):
        if not db.get(Product, values["product_id"]) or not group or group.kind != "product":
            raise BadRequestException("产品标签须属于产品分类系统并关联有效产品")
    seen = {tag_id} if tag_id else set()
    while parent_id:
        if parent_id in seen:
            raise BadRequestException("分类层级不能形成循环")
        seen.add(parent_id)
        parent = db.get(Tag, parent_id)
        if not parent or parent.group_id != group_id:
            raise BadRequestException("父分类须属于同一分类系统")
        parent_id = parent.parent_id
    if tag_id:
        children = db.query(Tag).filter_by(parent_id=tag_id).all()
        if any(child.group_id != group_id for child in children):
            raise BadRequestException("存在子分类，不能迁移到其他分类系统")
    duplicate = db.query(Tag).filter(Tag.name == name, Tag.group_id == group_id)
    if tag_id:
        duplicate = duplicate.filter(Tag.id != tag_id)
    if duplicate.first():
        raise BadRequestException("该系统内已有同名标签")


def tag_path(tag, by_id):
    parts, seen = [], set()
    while tag and tag.id not in seen:
        seen.add(tag.id)
        parts.append(tag.name)
        tag = by_id.get(tag.parent_id)
    return " / ".join(reversed(parts))


def classification_fields(db):
    if db is None:
        return []
    tags = db.query(Tag).all()
    by_id = {tag.id: tag for tag in tags}
    return [{"key": f"taxonomy_{group.id}", "name": group.name, "field_type": "taxonomy",
             "group_name": "分类系统", "taxonomy_group_id": group.id,
             "options": [str(tag.id) for tag in tags if tag.group_id == group.id],
             "option_labels": {str(tag.id): tag_path(tag, by_id) for tag in tags if tag.group_id == group.id},
             "width": 220, "sortable": False, "filterable": False, "editable": True,
             "frozen": False, "visible": True, "is_system": False, "versioned": False}
            for group in db.query(TagGroup).order_by(TagGroup.id).all()]


def apply_classification(db, patent_ids, tag_ids, mode, group_id, *, changed_by="local-user", source_view_id=None, source_view_name=None):
    from app.services.patent_service import PatentService, _stringify_value
    if mode not in {"add", "remove", "replace"}:
        raise BadRequestException("打标模式无效")
    group = db.get(TagGroup, group_id)
    if not group:
        raise NotFoundException("分类系统不存在")
    tags = db.query(Tag).filter(Tag.id.in_(tag_ids)).all() if tag_ids else []
    if len({tag.id for tag in tags}) != len(set(tag_ids)) or any(tag.group_id != group_id for tag in tags):
        raise BadRequestException("选定标签不属于该分类系统")
    patents = PatentService._load_bulk_patents(db, patent_ids, require_nonempty=True)
    changed = 0
    for patent in patents:
        current = set(patent.tags)
        scoped = {tag for tag in current if tag.group_id == group_id}
        selected = set(tags)
        next_scoped = scoped | selected if mode == "add" else scoped - selected if mode == "remove" else selected
        result = (current - scoped) | next_scoped
        if result == current:
            continue
        patent.tags = sorted(result, key=lambda tag: tag.id)
        if group.kind == "product":
            sync_product_tags(db, patent, from_tags=True)
        db.add(PatentHistory(patent_id=patent.id, field_key=f"taxonomy_{group_id}",
                             field_display_name=group.name,
                             old_value=_stringify_value(sorted(tag.id for tag in scoped)),
                             new_value=_stringify_value(sorted(tag.id for tag in next_scoped)),
                             source="manual", changed_by=changed_by,
                             source_view_id=source_view_id, source_view_name=source_view_name))
        from app.services.semantic_index_service import SemanticIndexService
        SemanticIndexService.enqueue_patent(db, patent.id, "classification_updated")
        changed += 1
    db.commit()
    return {"success": True, "updated_count": changed}


def export_config(db, group_ids):
    groups = db.query(TagGroup).filter(TagGroup.id.in_(group_ids)).all()
    if len(groups) != len(set(group_ids)):
        raise BadRequestException("分类系统不存在")
    systems = []
    for group in groups:
        tags = db.query(Tag).filter_by(group_id=group.id).order_by(Tag.id).all()
        nodes = []
        for tag in tags:
            product = db.get(Product, tag.product_id) if tag.product_id else None
            nodes.append({"key": str(tag.id), "parent_key": str(tag.parent_id) if tag.parent_id else None,
                          "name": tag.name, "color": tag.color, "description": tag.description,
                          "product": {"name": product.name, "code": product.code, "category": product.category} if product else None})
        systems.append({"name": group.name, "kind": group.kind, "color": group.color,
                        "description": group.description, "nodes": nodes})
    return {"format": "patwiki-classifications", "version": 1, "systems": systems}


def import_config(db, config):
    if config.get("format") != "patwiki-classifications" or config.get("version") != 1:
        raise BadRequestException("不支持的分类配置格式或版本")
    systems = config.get("systems")
    if not isinstance(systems, list) or not systems or len(systems) > 100:
        raise BadRequestException("配置须包含 1 至 100 个分类系统")
    names = set()
    try:
        for system in systems:
            name = system["name"].strip()
            kind = system.get("kind", "classification")
            if not name or len(name) > 100 or name in names or kind not in {"classification", "product"}:
                raise BadRequestException("分类系统名称或类型无效")
            names.add(name)
            group = db.query(TagGroup).filter_by(name=name).first()
            if group and group.kind != kind:
                raise BadRequestException("同名分类系统类型不一致")
            if not group:
                group = TagGroup(name=name, kind=kind, color=system.get("color"), description=system.get("description"))
                db.add(group)
                db.flush()
            nodes = system["nodes"]
            if not isinstance(nodes, list) or len(nodes) > 10000:
                raise BadRequestException("分类节点数量无效")
            keys = [node["key"] for node in nodes]
            if any(not isinstance(key, str) for key in keys) or len(keys) != len(set(keys)):
                raise BadRequestException("节点键重复或无效")
            pending, mapped = list(nodes), {}
            while pending:
                ready = [node for node in pending if not node.get("parent_key") or node["parent_key"] in mapped]
                if not ready:
                    raise BadRequestException("分类节点存在循环或缺失父节点")
                for node in ready:
                    parent_id = mapped.get(node.get("parent_key"))
                    tag = db.query(Tag).filter_by(group_id=group.id, name=node["name"]).first()
                    if tag and tag.parent_id != parent_id:
                        raise BadRequestException("同名节点层级冲突，整份配置未导入")
                    product_id = None
                    product_data = node.get("product")
                    if product_data:
                        if kind != "product":
                            raise BadRequestException("普通分类系统不能包含产品节点")
                        product = db.query(Product).filter_by(code=product_data["code"]).first() if product_data.get("code") else None
                        product = product or db.query(Product).filter_by(name=product_data["name"]).first()
                        if not product:
                            product = Product(name=product_data["name"], code=product_data.get("code"), category=product_data.get("category"))
                            db.add(product)
                            db.flush()
                        product_id = product.id
                    values = {"name": node["name"], "group_id": group.id, "parent_id": parent_id,
                              "product_id": product_id, "color": node.get("color"), "description": node.get("description")}
                    validate_tag(db, values, tag.id if tag else None)
                    if not tag:
                        tag = Tag(**values)
                        db.add(tag)
                    else:
                        for key, value in values.items():
                            setattr(tag, key, value)
                    db.flush()
                    mapped[node["key"]] = tag.id
                    pending.remove(node)
        db.commit()
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        db.rollback()
        raise BadRequestException("分类配置结构无效") from exc
    except Exception:
        db.rollback()
        raise
    return {"success": True, "imported_systems": len(systems)}
