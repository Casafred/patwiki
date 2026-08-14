# PatWiki 重构治理数据集

本目录是字段、关系、治理与路线图的 UTF-8 CSV 文本化维护源。转换前的 Office 版本不再保留在工作树中，可通过 Git 历史追溯；后续需求、字段和路线图只以本目录与配套 Markdown 为准。

## 使用方式

- `index.json` 是工作表与 CSV 文件的机器可读索引。
- `00-00_使用说明.csv` 至 `11-11_自动化与MCP.csv` 是从原工作簿逐表无损导出的事实台账。
- `12-实施基线与迁移门禁.csv` 是以当前代码架构复核后新增的开发门禁。它优先于旧工作簿中的“已具备能力”表述。
- 2026 范围以 `../PatWiki_refactor_guidance_pack/23-2026-product-scope-and-business-rules.md` 为准，专利详情和导入行为以 `../PatWiki_refactor_guidance_pack/24-patent-information-hub-functional-spec.md` 为准，开发门禁以 `../PatWiki_refactor_guidance_pack/21-implementation-contract.md` 为准；业务报告以 `../PatWiki_IP业务数据体系重构指导报告.md` 为准。

## 维护规则

1. CSV 使用 UTF-8、双引号包裹字段值；不要把逗号分隔 ID、JSON ID 数组或自由文本关系写回数据集。
2. 修改字段语义时，同时更新归一化字段字典、别名规则、迁移状态和对应的 Markdown 决策文档。
3. 每个来源字段必须处于 `candidate`、`unmapped_retained`、`mapped`、`deprecated` 或 `quarantined` 状态之一。未识别属性默认保留来源文件、工作表、行号和原始值；只有真正无法解析或身份冲突的行才进入 `quarantined`。
4. 任何“当前仓库能力”变更都必须先在 `12-实施基线与迁移门禁.csv` 更新，并链接到源码和测试。
5. 转换前的 Office 表达只可从 Git 历史追溯，不能反向覆盖文本源。
