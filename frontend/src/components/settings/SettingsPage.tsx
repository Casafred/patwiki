import { useState, useEffect, useCallback } from 'react'
import { settingsApi } from '../../api'
import { getErrorMessage } from '../../lib/errors'

export default function SettingsPage() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [hasApiKey, setHasApiKey] = useState(false)

  const [llm, setLLM] = useState({
    llm_provider: 'deepseek',
    llm_api_key: '',
    llm_model: 'deepseek-v4-flash',
    llm_base_url: 'https://api.deepseek.com',
    llm_temperature: 0.2,
    llm_max_tokens: 2000,
    llm_thinking_mode: 'disabled',
    llm_reasoning_effort: 'low',
  })
  const [aiBatchConcurrency, setAiBatchConcurrency] = useState(3)
  const [aiUseCache, setAiUseCache] = useState(true)

  // 用户是否手动改过 API key（避免把脱敏值回传）
  const [apiKeyEdited, setApiKeyEdited] = useState(false)
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)
  const [saveMsg, setSaveMsg] = useState('')

  const loadSettings = useCallback(async () => {
    try {
      const data = await settingsApi.get()
      const llmData = data.llm
      if (llmData && typeof llmData === 'object' && !Array.isArray(llmData)) {
        setLLM((prev) => ({ ...prev, ...(llmData as Partial<typeof prev>) }))
      }
      if (typeof data.has_api_key === 'boolean') setHasApiKey(data.has_api_key)
      if (typeof data.ai_batch_concurrency === 'number') setAiBatchConcurrency(data.ai_batch_concurrency)
      if (typeof data.ai_use_cache === 'boolean') setAiUseCache(data.ai_use_cache)
    } catch (e) {
      console.error('Failed to load settings:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // Settings are loaded from the backend after the component mounts.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadSettings()
  }, [loadSettings])

  const handleSave = async () => {
    setSaving(true)
    setSaveMsg('')
    try {
      const payload = {
        llm: {
          ...llm,
          // 若用户没改 api_key，传空字符串让后端保留原值
          llm_api_key: apiKeyEdited ? llm.llm_api_key : '',
        },
        ai_batch_concurrency: aiBatchConcurrency,
        ai_use_cache: aiUseCache,
      }
      const result = await settingsApi.update(payload)
      setSaveMsg(result.message || '保存成功')
      setApiKeyEdited(false)
      // 重新加载脱敏值
      await loadSettings()
    } catch (error: unknown) {
      setSaveMsg('保存失败: ' + getErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const result = await settingsApi.testLLM({
        api_key: apiKeyEdited ? llm.llm_api_key : '',
        provider: llm.llm_provider,
        base_url: llm.llm_base_url,
        model: llm.llm_model,
        temperature: llm.llm_temperature,
        max_tokens: llm.llm_max_tokens,
        thinking_mode: llm.llm_thinking_mode,
        reasoning_effort: llm.llm_reasoning_effort,
      })
      setTestResult(result)
    } catch (error: unknown) {
      setTestResult({
        success: false,
        message: getErrorMessage(error, '测试失败'),
      })
    } finally {
      setTesting(false)
    }
  }

  if (loading) {
    return (
      <div className="loading-spinner">
        <div className="spinner"></div>
        加载中...
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 700 }}>
      <div className="page-header">
        <h2 className="page-title">设置</h2>
        <p className="page-subtitle">配置 LLM API 以启用 AI 字段抽取功能</p>
      </div>

      {/* LLM 配置卡片 */}
      <div style={{
        background: 'white',
        border: '1px solid #e2e8f0',
        borderRadius: 8,
        padding: 24,
        marginBottom: 20,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>LLM 配置</h3>
          {hasApiKey ? (
            <span style={{ padding: '2px 8px', background: '#dcfce7', color: '#16a34a', borderRadius: 12, fontSize: 11 }}>已配置</span>
          ) : (
            <span style={{ padding: '2px 8px', background: '#fef2f2', color: '#dc2626', borderRadius: 12, fontSize: 11 }}>未配置</span>
          )}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <label style={{ display: 'block', fontSize: 13, color: '#475569', marginBottom: 6, fontWeight: 500 }}>
              API Provider
            </label>
            <select
              className="form-input"
              value={llm.llm_provider}
              onChange={(e) => {
                const provider = e.target.value
                if (provider === 'deepseek') {
                  setLLM({
                    ...llm,
                    llm_provider: provider,
                    llm_base_url: 'https://api.deepseek.com',
                    llm_model: 'deepseek-v4-flash',
                    llm_thinking_mode: 'disabled',
                    llm_reasoning_effort: 'low',
                  })
                } else {
                  setLLM({ ...llm, llm_provider: provider })
                }
              }}
            >
              <option value="deepseek">DeepSeek V4 Flash（官方）</option>
              <option value="openai">OpenAI 兼容（含国内代理）</option>
              <option value="anthropic">Anthropic Claude</option>
              <option value="custom">自定义</option>
            </select>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 13, color: '#475569', marginBottom: 6, fontWeight: 500 }}>
              API Key {!hasApiKey && <span style={{ color: '#dc2626' }}>*</span>}
            </label>
            <input
              type="password"
              className="form-input"
              value={llm.llm_api_key}
              onChange={(e) => {
                setLLM({ ...llm, llm_api_key: e.target.value })
                setApiKeyEdited(true)
              }}
              placeholder={hasApiKey ? '已配置（输入新值可覆盖）' : 'sk-... 或国内代理 API Key'}
            />
            <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>
              DeepSeek 使用平台 API Key；也可切换到其他 OpenAI 兼容服务。
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 13, color: '#475569', marginBottom: 6, fontWeight: 500 }}>
              Base URL
            </label>
            <input
              className="form-input"
              value={llm.llm_base_url}
              onChange={(e) => setLLM({ ...llm, llm_base_url: e.target.value })}
              placeholder="https://api.openai.com/v1"
            />
            <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>
              常见值：<br />
              • OpenAI: https://api.openai.com/v1<br />
              • DeepSeek 官方: https://api.deepseek.com<br />
              • 通义千问: https://dashscope.aliyuncs.com/compatible-mode/v1<br />
              • 智谱: https://open.bigmodel.cn/api/paas/v4<br />
              • Moonshot: https://api.moonshot.cn/v1
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 13, color: '#475569', marginBottom: 6, fontWeight: 500 }}>
              模型名称
            </label>
            <input
              className="form-input"
              value={llm.llm_model}
              onChange={(e) => setLLM({ ...llm, llm_model: e.target.value })}
              placeholder="deepseek-v4-flash / gpt-4o-mini / qwen-plus 等"
            />
          </div>

          {llm.llm_provider === 'deepseek' && (
            <div style={{ display: 'flex', gap: 16 }}>
              <div style={{ flex: 1 }}>
                <label style={{ display: 'block', fontSize: 13, color: '#475569', marginBottom: 6, fontWeight: 500 }}>
                  思考模式
                </label>
                <select
                  className="form-input"
                  value={llm.llm_thinking_mode}
                  onChange={(e) => setLLM({ ...llm, llm_thinking_mode: e.target.value })}
                >
                  <option value="disabled">关闭（推荐用于字段抽取）</option>
                  <option value="enabled">开启</option>
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <label style={{ display: 'block', fontSize: 13, color: '#475569', marginBottom: 6, fontWeight: 500 }}>
                  推理强度
                </label>
                <select
                  className="form-input"
                  value={llm.llm_reasoning_effort}
                  disabled={llm.llm_thinking_mode !== 'enabled'}
                  onChange={(e) => setLLM({ ...llm, llm_reasoning_effort: e.target.value })}
                >
                  <option value="low">低</option>
                  <option value="high">高</option>
                  <option value="max">最高</option>
                </select>
              </div>
            </div>
          )}

          <div style={{ display: 'flex', gap: 16 }}>
            <div style={{ flex: 1 }}>
              <label style={{ display: 'block', fontSize: 13, color: '#475569', marginBottom: 6, fontWeight: 500 }}>
                Temperature
              </label>
              <input
                type="number"
                step="0.1"
                min="0"
                max="2"
                className="form-input"
                value={llm.llm_temperature}
                onChange={(e) => setLLM({ ...llm, llm_temperature: Number(e.target.value) })}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ display: 'block', fontSize: 13, color: '#475569', marginBottom: 6, fontWeight: 500 }}>
                Max Tokens
              </label>
              <input
                type="number"
                min="1"
                max="384000"
                className="form-input"
                value={llm.llm_max_tokens}
                onChange={(e) => setLLM({ ...llm, llm_max_tokens: Number(e.target.value) })}
              />
            </div>
          </div>

          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <button className="btn btn-secondary" onClick={handleTest} disabled={testing || (!hasApiKey && !apiKeyEdited)}>
              {testing ? '测试中...' : '测试连接'}
            </button>
            <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
              {saving ? '保存中...' : '保存设置'}
            </button>
          </div>

          {testResult && (
            <div style={{
              padding: 12,
              borderRadius: 6,
              background: testResult.success ? '#f0fdf4' : '#fef2f2',
              border: `1px solid ${testResult.success ? '#bbf7d0' : '#fecaca'}`,
              fontSize: 13,
              color: testResult.success ? '#15803d' : '#b91c1c',
            }}>
              {testResult.message}
            </div>
          )}

          {saveMsg && (
            <div style={{
              padding: 12,
              borderRadius: 6,
              background: '#eff6ff',
              border: '1px solid #bfdbfe',
              fontSize: 13,
              color: '#1e40af',
            }}>
              {saveMsg}
            </div>
          )}
        </div>
      </div>

      {/* AI 高级配置 */}
      <div style={{
        background: 'white',
        border: '1px solid #e2e8f0',
        borderRadius: 8,
        padding: 24,
        marginBottom: 20,
      }}>
        <h3 style={{ margin: '0 0 16 0', fontSize: 16, fontWeight: 600 }}>AI 高级配置</h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <label style={{ display: 'block', fontSize: 13, color: '#475569', marginBottom: 6, fontWeight: 500 }}>
              批量处理并发数
            </label>
            <input
              type="number"
              min="1"
              max="10"
              className="form-input"
              style={{ maxWidth: 120 }}
              value={aiBatchConcurrency}
              onChange={(e) => setAiBatchConcurrency(Number(e.target.value))}
            />
            <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>
              控制 AI 批量处理时同时发起的请求数（1-10）。PatWiki 会在此上限内并发请求、串行写入本地数据库；较高值可能触发服务商限流。
            </div>
          </div>

          <div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#475569', fontWeight: 500, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={aiUseCache}
                onChange={(e) => setAiUseCache(e.target.checked)}
              />
              启用结果缓存
            </label>
            <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 4, marginLeft: 24 }}>
              对相同输入跳过 API 调用直接返回缓存结果，节省费用。关闭后每次都重新调用。
            </div>
          </div>

          <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>

      {/* 数据目录信息 */}
      <div style={{
        background: '#f8fafc',
        border: '1px solid #e2e8f0',
        borderRadius: 8,
        padding: 16,
      }}>
        <h3 style={{ margin: '0 0 8 0', fontSize: 14, fontWeight: 600, color: '#475569' }}>数据目录</h3>
        <p style={{ margin: 0, fontSize: 12, color: '#64748b' }}>
          数据库、AI 缓存、设置文件等均存储在用户数据目录下，卸载应用不会删除。
          <br />
          Windows: <code>%LOCALAPPDATA%/PatWiki/</code>
        </p>
      </div>
    </div>
  )
}
