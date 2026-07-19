from app.database import SessionLocal, init_db
from app.models import Department, TagGroup, CustomField, CustomFieldType


def init_default_data():
    db = SessionLocal()
    try:
        if db.query(Department).count() == 0:
            departments = [
                Department(name="检索组", description="负责专利检索、数据收集、竞品监控"),
                Department(name="分析组", description="负责专利分析、风险评估、技术主题梳理"),
                Department(name="撰写组", description="负责专利申请撰写、答复审查意见"),
            ]
            db.add_all(departments)
            db.flush()

        if db.query(TagGroup).count() == 0:
            tag_groups = [
                TagGroup(name="技术领域", color="#1890ff", description="按技术分类的标签组"),
                TagGroup(name="风险等级", color="#ff4d4f", description="专利风险标签"),
                TagGroup(name="项目状态", color="#52c41a", description="项目关联状态"),
                TagGroup(name="质量标签", color="#faad14", description="专利质量评估"),
            ]
            db.add_all(tag_groups)

        default_ai_fields = [
            {
                "key": "ai_technical_problem",
                "name": "AI提取-技术问题",
                "field_type": CustomFieldType.AI_FIELD,
                "group_name": "AI抽取",
                "description": "从专利文本中自动提取本专利要解决的技术问题",
                "sort_order": 1,
                "ai_config": {
                    "prompt_template": """请阅读以下专利信息，提取该专利要解决的**技术问题**。
要求：
1. 用简洁准确的语言描述，不超过100字
2. 聚焦于技术层面的问题，不要泛泛而谈
3. 如果无法确定，返回"未明确说明"

专利标题：{title}
专利摘要：{abstract}

直接给出技术问题："""
                },
            },
            {
                "key": "ai_technical_solution",
                "name": "AI提取-技术方案",
                "field_type": CustomFieldType.AI_FIELD,
                "group_name": "AI抽取",
                "description": "从专利文本中自动提取核心技术方案",
                "sort_order": 2,
                "ai_config": {
                    "prompt_template": """请阅读以下专利信息，提取该专利的**核心技术方案**。
要求：
1. 分点概括关键技术手段，不超过200字
2. 突出与现有技术的区别点
3. 结构清晰，便于快速理解

专利标题：{title}
专利摘要：{abstract}

直接给出技术方案要点："""
                },
            },
            {
                "key": "ai_technical_effect",
                "name": "AI提取-技术效果",
                "field_type": CustomFieldType.AI_FIELD,
                "group_name": "AI抽取",
                "description": "从专利文本中自动提取能达到的技术效果",
                "sort_order": 3,
                "ai_config": {
                    "prompt_template": """请阅读以下专利信息，提取该专利能够实现的**技术效果/有益效果**。
要求：
1. 列出主要的有益效果，不超过150字
2. 效果要与技术方案对应，具体可衡量
3. 如果无法确定，返回"未明确说明"

专利标题：{title}
专利摘要：{abstract}

直接给出技术效果："""
                },
            },
            {
                "key": "ai_risk_assessment",
                "name": "AI风险初评",
                "field_type": CustomFieldType.AI_FIELD,
                "group_name": "AI抽取",
                "description": "AI初步评估专利侵权风险等级",
                "sort_order": 4,
                "ai_config": {
                    "prompt_template": """请阅读以下专利信息，从**我方产品可能侵权的角度**进行初步风险评估。
要求：
1. 风险等级分为：高/中/低/无
2. 简要说明理由（50字以内）
3. 输出格式：风险等级：X，理由：XXX

专利标题：{title}
专利摘要：{abstract}
申请人：{applicant}
法律状态：{legal_status}

给出你的评估："""
                },
            },
            {
                "key": "ai_keywords",
                "name": "AI关键词",
                "field_type": CustomFieldType.AI_FIELD,
                "group_name": "AI抽取",
                "description": "自动提取专利核心技术关键词",
                "sort_order": 5,
                "ai_config": {
                    "prompt_template": """请阅读以下专利信息，提取5-8个最核心的**技术关键词**。
要求：
1. 关键词要精准代表该专利的技术主题
2. 用英文逗号分隔
3. 不要加序号或其他符号

专利标题：{title}
专利摘要：{abstract}

直接给出关键词："""
                },
            },
            {
                "key": "ai_summary",
                "name": "AI摘要总结",
                "field_type": CustomFieldType.AI_FIELD,
                "group_name": "AI抽取",
                "description": "一句话总结专利核心创新点",
                "sort_order": 6,
                "ai_config": {
                    "prompt_template": """请用**一句话**（不超过80字）总结下面这件专利的核心创新点和价值。
要求：语言精炼，突出"做了什么+解决了什么+好在哪里"。

专利标题：{title}
专利摘要：{abstract}

一句话总结："""
                },
            },
        ]

        for f in default_ai_fields:
            existing = db.query(CustomField).filter(CustomField.key == f["key"]).first()
            if not existing:
                db.add(CustomField(**f))

        db.commit()
        print("✅ 默认数据初始化完成！")
        print("   - 3个默认部门：检索组、分析组、撰写组")
        print("   - 4个标签组：技术领域、风险等级、项目状态、质量标签")
        print(f"   - {len(default_ai_fields)}个AI字段模板")
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    init_default_data()
