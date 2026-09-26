import { useMemo, useState } from "react";
import type { JsonObject, JsonValue, Patent } from "../../types";
import { aiService } from "../../services";
import { getErrorMessage } from "../../lib/errors";
import Icon from "../common/Icon";

interface Props {
  patents: Patent[];
  onClose: () => void;
}
type QuestionType = "choice" | "score" | "noul";
interface MarkItem {
  key: string;
  name: string;
  type: QuestionType;
  instructions: string;
  options: string[];
  review: boolean;
  output: "preview" | "tag" | "field";
}
interface JEVResult {
  model: string;
  answers: JsonObject;
  usage?: JsonObject | null;
}

const GENERAL: MarkItem[] = [
  {
    key: "technical_relevance",
    name: "技术主题相关性",
    type: "choice",
    instructions: "根据标题、摘要和权利要求，判断该专利与目标技术主题的关系。",
    options: ["核心相关", "部分相关", "不相关"],
    review: false,
    output: "tag",
  },
  {
    key: "needs_review",
    name: "是否需要人工复核",
    type: "noul",
    instructions: "判断 AI 结果是否需要交由专利人员复核后再使用。",
    options: [],
    review: true,
    output: "preview",
  },
  {
    key: "priority",
    name: "标引优先级",
    type: "score",
    instructions: "结合技术相关性和信息完整度，给出人工标引的优先级。",
    options: ["低", "中", "高"],
    review: false,
    output: "field",
  },
];
const TRIAGE: MarkItem[] = [
  {
    key: "ipc_theme",
    name: "技术主题匹配度",
    type: "choice",
    instructions:
      "参考摘要、权利要求及 IPC/CPC 信息，判断专利属于目标技术主题的程度。",
    options: ["核心相关", "相邻技术", "不相关"],
    review: true,
    output: "tag",
  },
  {
    key: "patent_type",
    name: "专利类型",
    type: "choice",
    instructions: "判断保护客体和专利类型。无法确定时选择无法判断。",
    options: ["发明", "实用新型", "外观设计", "无法判断"],
    review: false,
    output: "field",
  },
  {
    key: "novelty_risk",
    name: "新颖性/创造性复核优先级",
    type: "score",
    instructions: "根据文本中体现的技术方案和风险线索，判断复核优先级。",
    options: ["低", "中", "高"],
    review: true,
    output: "field",
  },
  {
    key: "needs_review",
    name: "是否需要人工复核",
    type: "noul",
    instructions: "判断是否需要专利人员复核后再写入正式标注。",
    options: [],
    review: true,
    output: "preview",
  },
];
const displayKey = (key: string) =>
  ({
    technical_relevance: "技术相关性",
    ipc_theme: "技术主题匹配度",
    patent_type: "专利类型",
    novelty_risk: "新颖性/创造性复核优先级",
    needs_review: "是否需要人工复核",
    priority: "标引优先级",
    confidence: "置信度",
    reason: "判断依据",
    explanation: "判断说明",
  })[key] ||
  key.replace(/[_-]+/g, " ").replace(/\b\w/g, (s) => s.toUpperCase());
const valueText = (value: JsonValue | undefined): string => {
  if (value === undefined || value === null) return "未返回";
  if (typeof value === "object")
    return Array.isArray(value)
      ? value.map(valueText).join("、")
      : Object.entries(value)
          .map(([k, v]) => `${displayKey(k)}：${valueText(v)}`)
          .join("；");
  return String(value);
};
const toQuestions = (items: MarkItem[]): JsonObject =>
  Object.fromEntries(
    items.map((item) => [
      item.key,
      {
        type: item.type,
        instructions: item.instructions,
        criteria: item.type === "noul" ? undefined : item.options,
      },
    ]),
  ) as JsonObject;

export default function JEVQuickAnalyzeModal({ patents, onClose }: Props) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [template, setTemplate] = useState<"general" | "triage" | "custom">(
    "general",
  );
  const [items, setItems] = useState<MarkItem[]>(GENERAL);
  const [advanced, setAdvanced] = useState(false);
  const [advancedText, setAdvancedText] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<JEVResult | null>(null);
  const [patentIndex, setPatentIndex] = useState(0);
  const [reviewed, setReviewed] = useState<Record<number, boolean>>({});
  const [edits, setEdits] = useState<Record<string, string>>({});
  const current = patents[patentIndex];
  const state = useMemo(
    () => ({
      records: patents.map((p) => ({
        id: p.id,
        title: p.title,
        abstract: p.abstract || "",
        claims: p.claims || "",
        application_number: p.application_number || "",
        publication_number: p.publication_number || "",
        ipc: p.ipc_all || p.ipc_main || "",
      })),
    }),
    [patents],
  );
  const chooseTemplate = (value: "general" | "triage" | "custom") => {
    setTemplate(value);
    if (value === "custom") {
      setItems([]);
      setAdvancedText("");
    } else {
      const next = value === "triage" ? TRIAGE : GENERAL;
      setItems(next);
      setAdvancedText(JSON.stringify(toQuestions(next), null, 2));
    }
  };
  const updateItem = (index: number, patch: Partial<MarkItem>) => {
    setTemplate("custom");
    setItems((prev) =>
      prev.map((item, i) => (i === index ? { ...item, ...patch } : item)),
    );
  };
  const addItem = () => {
    setTemplate("custom");
    setItems((prev) => [
      ...prev,
      {
        key: `mark_${prev.length + 1}`,
        name: "新的标注项",
        type: "choice",
        instructions: "请填写判断说明。",
        options: ["是", "否"],
        review: true,
        output: "preview",
      },
    ]);
  };
  const run = async () => {
    setError("");
    setRunning(true);
    try {
      let questions = toQuestions(items);
      if (advanced && advancedText.trim())
        questions = JSON.parse(advancedText) as JsonObject;
      const response = await aiService.jevAnalyze({ state, questions });
      setResult(response);
      setStep(3);
    } catch (e) {
      setError(
        getErrorMessage(e, "JEV 分析失败，请检查标注项和 AI 能力中心配置"),
      );
    } finally {
      setRunning(false);
    }
  };
  const answerEntries = result ? Object.entries(result.answers || {}) : [];
  return (
    <div
      className="modal-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className="modal-content jev-quick-analyze-modal"
        style={{
          width: "min(1120px, 96vw)",
          maxHeight: "92vh",
          overflow: "auto",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <h3>
              <Icon name="sparkles" size={16} /> JEV 快速标引
            </h3>
            <p className="modal-subtitle">
              面向专利分类、标注和复核的引导式工作台，结果只在人工确认后使用。
            </p>
          </div>
          <button className="icon-button" onClick={onClose} title="关闭">
            <Icon name="x" />
          </button>
        </div>
        <div
          style={{
            display: "flex",
            gap: 6,
            marginBottom: 16,
            borderBottom: "1px solid #e2e8f0",
            paddingBottom: 12,
          }}
        >
          {(["选择任务", "配置标注", "运行与复核"] as const).map(
            (name, index) => (
              <button
                key={name}
                className={`btn btn-xs ${step === index + 1 ? "btn-primary" : "btn-secondary"}`}
                onClick={() => setStep((index + 1) as 1 | 2 | 3)}
              >
                {index + 1}. {name}
              </button>
            ),
          )}
        </div>
        {step === 1 && (
          <div>
            <div style={{ marginBottom: 14 }}>
              <strong style={{ fontSize: 15 }}>你要处理什么任务？</strong>
              <p style={{ color: "#64748b", fontSize: 12, margin: "5px 0" }}>
                选择一个起点，之后仍可逐项修改。
              </p>
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                gap: 12,
              }}
            >
              {[
                [
                  "general",
                  "通用专利初筛",
                  "判断技术相关性、优先级和是否需要复核。",
                ],
                [
                  "triage",
                  "分类与风险分流",
                  "辅助判断 IPC 主题、专利类型和新颖性风险。",
                ],
                [
                  "custom",
                  "自定义标注任务",
                  "从空白任务开始，按你的业务字段设计。",
                ],
              ].map(([value, title, description]) => (
                <button
                  key={value}
                  onClick={() =>
                    chooseTemplate(value as "general" | "triage" | "custom")
                  }
                  style={{
                    textAlign: "left",
                    padding: 16,
                    background: template === value ? "#ecfeff" : "#fff",
                    border: `1px solid ${template === value ? "#0f766e" : "#dbe4ea"}`,
                    borderRadius: 8,
                    cursor: "pointer",
                  }}
                >
                  <div
                    style={{
                      fontWeight: 700,
                      color: "#0f172a",
                      marginBottom: 7,
                    }}
                  >
                    {title}
                  </div>
                  <div
                    style={{ color: "#64748b", fontSize: 12, lineHeight: 1.6 }}
                  >
                    {description}
                  </div>
                </button>
              ))}
            </div>
            <div
              style={{
                marginTop: 18,
                padding: 14,
                background: "#f8fafc",
                borderRadius: 8,
                color: "#475569",
                fontSize: 12,
              }}
            >
              <strong>本次处理范围：</strong> {patents.length} 条已选专利。JEV
              会读取标题、摘要、权利要求、申请号、公开号和 IPC 信息。
            </div>
          </div>
        )}
        {step === 2 && (
          <div>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 12,
              }}
            >
              <div>
                <strong style={{ fontSize: 15 }}>配置标注项</strong>
                <p style={{ color: "#64748b", fontSize: 12, margin: "5px 0" }}>
                  每一项都会成为结果中的一个清晰字段，不需要编写代码。
                </p>
              </div>
              <button className="btn btn-secondary btn-xs" onClick={addItem}>
                <Icon name="plus" size={13} /> 添加标注项
              </button>
            </div>
            <div style={{ display: "grid", gap: 10 }}>
              {items.map((item, index) => (
                <div
                  key={`${item.key}-${index}`}
                  style={{
                    border: "1px solid #dbe4ea",
                    borderRadius: 8,
                    padding: 12,
                    background: "#fff",
                  }}
                >
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns:
                        "minmax(160px, 1fr) 130px 120px auto",
                      gap: 8,
                      alignItems: "end",
                    }}
                  >
                    <label>
                      标注名称
                      <input
                        className="form-input"
                        value={item.name}
                        onChange={(e) =>
                          updateItem(index, { name: e.target.value })
                        }
                      />
                    </label>
                    <label>
                      判断方式
                      <select
                        className="form-input"
                        value={item.type}
                        onChange={(e) =>
                          updateItem(index, {
                            type: e.target.value as QuestionType,
                          })
                        }
                      >
                        <option value="choice">单选</option>
                        <option value="score">等级评分</option>
                        <option value="noul">是 / 否</option>
                      </select>
                    </label>
                    <label>
                      结果用途
                      <select
                        className="form-input"
                        value={item.output}
                        onChange={(e) =>
                          updateItem(index, {
                            output: e.target.value as MarkItem["output"],
                          })
                        }
                      >
                        <option value="preview">仅预览</option>
                        <option value="tag">生成标签</option>
                        <option value="field">写入字段</option>
                      </select>
                    </label>
                    <button
                      className="icon-button"
                      title="删除标注项"
                      onClick={() =>
                        setItems((prev) => prev.filter((_, i) => i !== index))
                      }
                    >
                      <Icon name="trash" size={15} />
                    </button>
                  </div>
                  <label style={{ display: "block", marginTop: 8 }}>
                    判断说明
                    <textarea
                      className="form-input"
                      rows={2}
                      value={item.instructions}
                      onChange={(e) =>
                        updateItem(index, { instructions: e.target.value })
                      }
                    />
                  </label>
                  {item.type !== "noul" && (
                    <label style={{ display: "block", marginTop: 8 }}>
                      可选结果（用逗号分隔）
                      <input
                        className="form-input"
                        value={item.options.join("、")}
                        onChange={(e) =>
                          updateItem(index, {
                            options: e.target.value
                              .split(/[、,，]/)
                              .map((v) => v.trim())
                              .filter(Boolean),
                          })
                        }
                      />
                    </label>
                  )}
                  <label
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                      marginTop: 8,
                      color: "#475569",
                      fontSize: 12,
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={item.review}
                      onChange={(e) =>
                        updateItem(index, { review: e.target.checked })
                      }
                    />{" "}
                    结果需要人工复核
                  </label>
                </div>
              ))}
            </div>
            <details
              open={advanced}
              onToggle={(e) =>
                setAdvanced((e.currentTarget as HTMLDetailsElement).open)
              }
              style={{ marginTop: 14 }}
            >
              <summary
                style={{ cursor: "pointer", color: "#64748b", fontSize: 12 }}
              >
                高级设置：查看 / 编辑结构化配置（JSON）
              </summary>
              <textarea
                className="form-input"
                rows={8}
                value={
                  advancedText || JSON.stringify(toQuestions(items), null, 2)
                }
                onChange={(e) => {
                  setAdvancedText(e.target.value);
                  setTemplate("custom");
                }}
                style={{ marginTop: 8, fontFamily: "monospace", fontSize: 12 }}
              />
            </details>
          </div>
        )}
        {step === 3 && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(240px, .75fr) minmax(420px, 1.25fr)",
              gap: 16,
            }}
          >
            <div style={{ minWidth: 0 }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: 8,
                }}
              >
                <strong>
                  {patents.length > 1
                    ? `第 ${patentIndex + 1} / ${patents.length} 条`
                    : "当前专利"}
                </strong>
                <span style={{ color: "#64748b", fontSize: 12 }}>
                  {reviewed[current?.id || 0] ? "已确认" : "待复核"}
                </span>
              </div>
              {patents.length > 1 && (
                <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
                  <button
                    className="btn btn-xs btn-secondary"
                    disabled={patentIndex === 0}
                    onClick={() => setPatentIndex((i) => i - 1)}
                  >
                    上一条
                  </button>
                  <button
                    className="btn btn-xs btn-secondary"
                    disabled={patentIndex === patents.length - 1}
                    onClick={() => setPatentIndex((i) => i + 1)}
                  >
                    下一条
                  </button>
                </div>
              )}
              <div
                style={{
                  border: "1px solid #dbe4ea",
                  borderRadius: 8,
                  padding: 13,
                  maxHeight: 480,
                  overflow: "auto",
                }}
              >
                <div style={{ fontWeight: 700, lineHeight: 1.5 }}>
                  {current?.title || "未选择专利"}
                </div>
                <div
                  style={{
                    color: "#64748b",
                    fontSize: 11,
                    margin: "7px 0 12px",
                  }}
                >
                  申请号：{current?.application_number || "未填写"} 公开号：
                  {current?.publication_number || "未填写"}
                  <br />
                  IPC：{current?.ipc_all || current?.ipc_main || "未填写"}
                </div>
                <div style={{ fontSize: 12, lineHeight: 1.7 }}>
                  <strong>摘要</strong>
                  <p
                    style={{
                      whiteSpace: "pre-wrap",
                      margin: "3px 0 12px",
                      color: "#475569",
                    }}
                  >
                    {current?.abstract || "暂无摘要"}
                  </p>
                  <strong>权利要求</strong>
                  <p
                    style={{
                      whiteSpace: "pre-wrap",
                      margin: "3px 0",
                      color: "#475569",
                    }}
                  >
                    {current?.claims || "暂无权利要求"}
                  </p>
                </div>
              </div>
            </div>
            <div>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: 8,
                }}
              >
                <strong>结构化判断结果</strong>
                {result && (
                  <span style={{ color: "#64748b", fontSize: 11 }}>
                    模型：{result.model}
                  </span>
                )}
              </div>
              {result ? (
                <div
                  style={{
                    border: "1px solid #dbe4ea",
                    borderRadius: 8,
                    overflow: "hidden",
                  }}
                >
                  {answerEntries.map(([key, value]) => (
                    <div
                      key={key}
                      style={{
                        padding: "12px 14px",
                        borderBottom: "1px solid #eef2f6",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          gap: 12,
                          marginBottom: 6,
                        }}
                      >
                        <strong>{displayKey(key)}</strong>
                        <span style={{ color: "#64748b", fontSize: 11 }}>
                          {key}
                        </span>
                      </div>
                      <input
                        className="form-input"
                        value={edits[key] ?? valueText(value)}
                        onChange={(e) =>
                          setEdits((prev) => ({
                            ...prev,
                            [key]: e.target.value,
                          }))
                        }
                      />
                      {(key === "needs_review" ||
                        key === "reason" ||
                        key === "explanation") && (
                        <div
                          style={{
                            marginTop: 6,
                            color: "#92400e",
                            background: "#fffbeb",
                            borderRadius: 5,
                            padding: "5px 8px",
                            fontSize: 11,
                          }}
                        >
                          建议由专利人员复核后再写入正式数据
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div
                  style={{
                    padding: 24,
                    background: "#f8fafc",
                    border: "1px dashed #cbd5e1",
                    borderRadius: 8,
                    color: "#64748b",
                    fontSize: 12,
                  }}
                >
                  先点击下方“运行 JEV
                  判断”，这里会显示可读的分类、评分、依据和复核提示。
                </div>
              )}
              <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                <button
                  className="btn btn-secondary"
                  disabled={!result}
                  onClick={() =>
                    setReviewed((prev) => ({
                      ...prev,
                      [current?.id || 0]: false,
                    }))
                  }
                >
                  标记待复核
                </button>
                <button
                  className="btn btn-primary"
                  disabled={!result}
                  onClick={() =>
                    setReviewed((prev) => ({
                      ...prev,
                      [current?.id || 0]: true,
                    }))
                  }
                >
                  <Icon name="check" size={14} /> 确认本条结果
                </button>
              </div>
            </div>
          </div>
        )}
        {error && (
          <div
            style={{
              color: "#b91c1c",
              background: "#fef2f2",
              padding: 10,
              marginTop: 12,
              borderRadius: 6,
              fontSize: 12,
            }}
          >
            {error}
          </div>
        )}
        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose}>
            关闭
          </button>
          {step === 1 && (
            <button className="btn btn-primary" onClick={() => setStep(2)}>
              下一步：配置标注
            </button>
          )}
          {step === 2 && (
            <>
              <button className="btn btn-secondary" onClick={() => setStep(1)}>
                上一步
              </button>
              <button
                className="btn btn-primary"
                onClick={() => void run()}
                disabled={running || patents.length === 0}
              >
                <Icon name="play" size={14} />{" "}
                {running ? "分析中..." : "运行 JEV 判断"}
              </button>
            </>
          )}
          {step === 3 && (
            <button className="btn btn-secondary" onClick={() => setStep(2)}>
              调整标注项
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
