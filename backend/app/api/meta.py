from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional

from app.database import get_db
from app.models import (
    Product, ProductLine, Project, Tag, TagGroup,
    CustomField, Department, Person, CustomFieldType,
    Patent,
)
from app.schemas.schemas import (
    Product as ProductSchema, ProductCreate, ProductUpdate,
    Project as ProjectSchema, ProjectCreate, ProjectUpdate,
    Tag as TagSchema, TagCreate, TagUpdate,
    TagGroup as TagGroupSchema, TagGroupCreate,
    CustomField as CustomFieldSchema, CustomFieldCreate, CustomFieldUpdate,
    Department as DepartmentSchema, DepartmentCreate,
    Person as PersonSchema, PersonCreate,
    ProductLine as ProductLineSchema, ProductLineCreate,
)

router = APIRouter(tags=["meta"])


@router.get("/products", response_model=list[ProductSchema])
def list_products(
    active_only: bool = False,
    database_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    列出产品分类。

    打通产品分类与库（Database）的关联关系：
    - 若指定 database_id，则 patent_count 返回该库下各产品的专利数；
    - 否则 patent_count 返回跨所有库的专利总数。
    - 产品本身仍是全局实体，不绑定到任何库，关联通过 Patent.product_id + Patent.database_id 体现。
    """
    query = db.query(Product)
    if active_only:
        query = query.filter(Product.is_active == True)
    products = query.order_by(Product.name).all()

    # 用一条聚合 SQL 一次性拿到所有 Product 的专利计数，避免 N+1
    count_query = db.query(
        Patent.product_id,
        func.count(Patent.id).label("cnt"),
    ).filter(Patent.product_id.isnot(None))
    if database_id is not None:
        count_query = count_query.filter(Patent.database_id == database_id)
    count_map = {pid: cnt for pid, cnt in count_query.group_by(Patent.product_id).all()}

    for p in products:
        p.patent_count = count_map.get(p.id, 0)
    return products


@router.post("/products", response_model=ProductSchema)
def create_product(product_in: ProductCreate, db: Session = Depends(get_db)):
    product = Product(**product_in.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.put("/products/{product_id}", response_model=ProductSchema)
def update_product(product_id: int, product_in: ProductUpdate, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    for field, value in product_in.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(product)
    db.commit()
    return {"success": True}


@router.get("/projects", response_model=list[ProjectSchema])
def list_projects(
    product_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Project)
    if product_id:
        query = query.filter(Project.product_id == product_id)
    projects = query.order_by(Project.name).all()
    for p in projects:
        p.patent_count = len(p.patents)
    return projects


@router.post("/projects", response_model=ProjectSchema)
def create_project(project_in: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(**project_in.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.put("/projects/{project_id}", response_model=ProjectSchema)
def update_project(project_id: int, project_in: ProjectUpdate, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    for field, value in project_in.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/projects/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()
    return {"success": True}


@router.get("/tags", response_model=list[TagSchema])
def list_tags(db: Session = Depends(get_db)):
    return db.query(Tag).order_by(Tag.name).all()


@router.post("/tags", response_model=TagSchema)
def create_tag(tag_in: TagCreate, db: Session = Depends(get_db)):
    tag = Tag(**tag_in.model_dump())
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


@router.put("/tags/{tag_id}", response_model=TagSchema)
def update_tag(tag_id: int, tag_in: TagUpdate, db: Session = Depends(get_db)):
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    for field, value in tag_in.model_dump(exclude_unset=True).items():
        setattr(tag, field, value)
    db.commit()
    db.refresh(tag)
    return tag


@router.delete("/tags/{tag_id}")
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    db.delete(tag)
    db.commit()
    return {"success": True}


@router.get("/tag-groups", response_model=list[TagGroupSchema])
def list_tag_groups(db: Session = Depends(get_db)):
    return db.query(TagGroup).order_by(TagGroup.name).all()


@router.post("/tag-groups", response_model=TagGroupSchema)
def create_tag_group(group_in: TagGroupCreate, db: Session = Depends(get_db)):
    group = TagGroup(**group_in.model_dump())
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


@router.get("/custom-fields", response_model=list[CustomFieldSchema])
def list_custom_fields(
    active_only: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(CustomField)
    if active_only:
        query = query.filter(CustomField.is_active == True)
    return query.order_by(CustomField.sort_order, CustomField.name).all()


@router.post("/custom-fields", response_model=CustomFieldSchema)
def create_custom_field(field_in: CustomFieldCreate, db: Session = Depends(get_db)):
    field = CustomField(**field_in.model_dump())
    db.add(field)
    db.commit()
    db.refresh(field)
    return field


@router.put("/custom-fields/{field_id}", response_model=CustomFieldSchema)
def update_custom_field(field_id: int, field_in: CustomFieldUpdate, db: Session = Depends(get_db)):
    field = db.query(CustomField).filter(CustomField.id == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    for field_name, value in field_in.model_dump(exclude_unset=True).items():
        setattr(field, field_name, value)
    db.commit()
    db.refresh(field)
    return field


@router.delete("/custom-fields/{field_id}")
def delete_custom_field(field_id: int, db: Session = Depends(get_db)):
    field = db.query(CustomField).filter(CustomField.id == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    db.delete(field)
    db.commit()
    return {"success": True}


@router.get("/departments", response_model=list[DepartmentSchema])
def list_departments(db: Session = Depends(get_db)):
    return db.query(Department).order_by(Department.name).all()


@router.post("/departments", response_model=DepartmentSchema)
def create_department(dept_in: DepartmentCreate, db: Session = Depends(get_db)):
    dept = Department(**dept_in.model_dump())
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


@router.get("/people", response_model=list[PersonSchema])
def list_people(db: Session = Depends(get_db)):
    return db.query(Person).order_by(Person.name).all()


@router.post("/people", response_model=PersonSchema)
def create_person(person_in: PersonCreate, db: Session = Depends(get_db)):
    person = Person(**person_in.model_dump())
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


@router.get("/product-lines", response_model=list[ProductLineSchema])
def list_product_lines(db: Session = Depends(get_db)):
    return db.query(ProductLine).order_by(ProductLine.name).all()


@router.post("/product-lines", response_model=ProductLineSchema)
def create_product_line(pl_in: ProductLineCreate, db: Session = Depends(get_db)):
    pl = ProductLine(**pl_in.model_dump())
    db.add(pl)
    db.commit()
    db.refresh(pl)
    return pl
