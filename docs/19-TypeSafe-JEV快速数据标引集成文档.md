# TypeSafe JEV 快速数据标引集成文档

## 1. 调研结论

本集成依据 TypeSafe AI 官方 Quickstart（访问日期：2026-09-21）：

- API：`POST <JEV 网关地址>/systemone`；官方地址为 `https://api.typesafe.ai/v1/systemone`，兔子中转地址为 `https://api.tu-zi.com/v1/systemone`
- 鉴权：`Authorization: Bearer <TYPESAFE_API_KEY>`
- 模型：`jev-latest`（响应会返回实际版本，例如 `jev-1.13.0`）
- 请求：`state`（待判断文本）+ `questions`（多个结构化问题）
- 问题类型：`choice`（分类）、`score`（等级评分）、`noul`（是/否或程度判断）
- 返回：每个问题的答案、置信度和概率；并带有 token usage

JEV 的优势是一次请求做多个维度的稳定判断，适合专利标题/摘要/权利要求的快速相关性筛选、技术主题分类、是否涉及某技术特征、标引优先级评分等。它不是通用聊天接口，不应把它当作自由文本长篇分析器；复杂解释、长文本抽取和需要严格 JSON schema 的任务仍使用现有 OpenAI-compatible LLM 链路。

## 2. PatWiki 中的配置

在设置页或 `PUT /api/settings` 保存：

```json
{
  "llm": {
    "llm_provider": "typesafe",
    "llm_api_key": "ts_...",
    "llm_model": "jev-1.13",
    "llm_base_url": "https://api.tu-zi.com/v1"
  },
  "ai_enabled": true
}
```

保存时会把 `jev` / `typesafe-ai` 别名规范化为 `typesafe`，并自动补齐官方默认模型和地址。兔子中转地址会被保留，模型可填 `jev-1.13`；响应中应记录服务端返回的实际版本（例如 `jev-1.13.0`）。API Key 只保存在本机 `data/settings.json`，读取设置时会脱敏。

## 3. 快速标引接口

接口：`POST /api/ai/jev-analyze`

请求示例：

```json
{
  "state": {"title": "一种用于降低神经网络推理延迟的缓存调度方法", "abstract": "包括按层级复用中间特征..."},
  "questions": {
    "technical_relevance": {
      "type": "choice",
      "instructions": "该文本的核心方案是否属于边缘AI推理优化？",
      "criteria": {
        "yes": "明确针对边缘设备或端侧推理优化",
        "partial": "涉及推理优化，但边缘场景不明确",
        "no": "与该主题无关"
      }
    },
    "priority": {
      "type": "score",
      "instructions": "按对当前技术路线的标引优先级评分",
      "criteria": ["低", "中", "高"]
    },
    "needs_review": {
      "type": "noul",
      "instructions": "是否需要人工复核后才能写入正式标引字段？"
    }
  }
}
```

返回示例：

```json
{
  "model": "jev-1.13.0",
  "answers": {
    "technical_relevance": {
      "type": "choice",
      "choice": "yes",
      "confidence": 0.91,
      "probabilities": {"yes": 0.91, "partial": 0.08, "no": 0.01}
    },
    "priority": {
      "type": "score",
      "score": 2.0,
      "confidence": 0.84,
      "legend": {"0": "低", "1": "中", "2": "高"}
    },
    "needs_review": {"type": "noul", "noul": 1.0}
  },
  "usage": {"input_tokens": 180, "output_tokens": 42}
}
```

应用侧建议把 `answers` 原样存入 AI 任务审计信息，把 `choice`/`score` 映射成草稿字段；只有人工确认后再写入正式业务字段。`confidence` 不是事实正确率，只是模型对当前判断的置信度，不能替代专利审查结论。界面入口位于专利表格中选中一条专利后的“JEV 标引”或“表格工具 -> JEV 快速标引”，用于先预览结构化结果；一个 JEV 请求对应一条专利，避免把一份聚合判断误用于多条记录。需要批量写入字段时，建议将审定后的标签配置为现有 AI 字段或人工批量编辑。

## 4. 调用边界与失败处理

后端统一服务 `app.services.llm_service.jev_system_one` 负责 URL、Bearer 鉴权、超时、429/5xx 重试和响应格式校验。JEV 失败不会静默写入字段；接口返回可展示的错误，后台任务应记录模型版本、请求摘要和 usage。

建议：

1. 批量标引先用 20-50 条样本评估准确率，再扩大范围。
2. 对低置信度、`choice` 概率接近的结果设置人工复核门槛。
3. `state` 只传完成脱敏的必要字段，避免发送无关个人信息或商业秘密。
4. 保存实际响应模型版本，避免 `jev-latest` 滚动升级造成结果不可复现。
5. 对 `choice` 的 criteria 使用稳定、互斥、覆盖完整的标签；对 `score` 明确每个等级含义。

## 5. 与现有 AI 功能的分工

| 场景 | 推荐实现 |
| --- | --- |
| 多维快速分类、相关性判断、优先级评分 | JEV `/api/ai/jev-analyze` |
| 从文本生成长摘要或复杂 JSON 抽取 | 现有 `quick-analyze` + OpenAI-compatible LLM |
| AI 字段批量计算并缓存 | 现有 AI 字段引擎；可继续使用 DeepSeek/OpenAI-compatible provider |
| 需要证据链、引用原文和人工确认 | JEV 判断 + PatWiki 审计/草稿字段，不直接覆盖正式值 |

## 6. 验证

离线契约测试：

```bash
cd backend
pytest tests/test_llm_service.py -q
```

真实连通性测试需要在 PatWiki 设置页填入 TypeSafe API Key 后点击“测试 LLM 连接”；测试请求只发送一个 `ping` state 和一个 Noul 问题。

参考：<https://docs.typesafe.ai/introduction/quickstart#call-it-the-api>
