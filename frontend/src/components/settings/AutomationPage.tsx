import { useCallback, useEffect, useState } from 'react'
import {
  automationService as automationApi,
  fieldService as fieldApi,
  patentService as patentApi,
} from '../../services'
import { useAppStore } from '../../store'
import type { AutomationLog, AutomationRule, FieldMeta, JsonObject } from '../../types'
import { getErrorMessage } from '../../lib/errors'

type TriggerType = 'manual' | 'record_created' | 'record_imported' | 'field_changed' | 'schedule'
type ActionType = 'set_field' | 'send_notification'

const triggerLabels: Record<TriggerType, string> = {
  manual: '手动执行', record_created: '记录创建', record_imported: '记录导入', field_changed: '字段变更', schedule: '定时执行',
}

function valueText(value: unknown, fallback = ''): string {
  return typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean' ? String(value) : fallback
}

export default function AutomationPage() {
  const { currentDatabaseId } = useAppStore()
  const [rules, setRules] = useState<AutomationRule[]>([])
  const [logs, setLogs] = useState<AutomationLog[]>([])
  const [fields, setFields] = useState<FieldMeta[]>([])
  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [triggerType, setTriggerType] = useState<TriggerType>('field_changed')
  const [triggerField, setTriggerField] = useState('legal_status')
  const [scheduleMinutes, setScheduleMinutes] = useState('60')
  const [conditionField, setConditionField] = useState('')
  const [conditionValue, setConditionValue] = useState('')
  const [actionType, setActionType] = useState<ActionType>('set_field')
  const [actionField, setActionField] = useState('module')
  const [actionValue, setActionValue] = useState('')
  const [notification, setNotification] = useState('专利自动化规则已执行')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    if (currentDatabaseId === null) return
    try {
      const [loadedRules, loadedLogs, loadedFields] = await Promise.all([
        automationApi.listRules(currentDatabaseId), automationApi.logs(currentDatabaseId), fieldApi.list(),
      ])
      setRules(loadedRules)
      setLogs(loadedLogs)
      setFields(loadedFields)
    } catch (loadError: unknown) {
      setError(getErrorMessage(loadError, '自动化数据加载失败'))
    }
  }, [currentDatabaseId])

  // Load rules when the active database changes.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void load() }, [load])

  const createRule = async () => {
    if (!currentDatabaseId || !name.trim() || !actionField.trim()) return
    setBusy(true); setError('')
    try {
      const trigger: JsonObject = { type: triggerType }
      if (triggerType === 'field_changed') trigger.field = triggerField
      if (triggerType === 'schedule') { trigger.schedule = `every:${scheduleMinutes}`; trigger.interval_minutes = Number(scheduleMinutes) }
      const conditions: JsonObject[] = conditionField.trim() ? [{ field: conditionField.trim(), op: '==', value: conditionValue }] : []
      const action: JsonObject = actionType === 'set_field'
        ? { type: actionType, field: actionField.trim(), value: actionValue }
        : { type: actionType, message: notification, channel: 'in_app' }
      await automationApi.createRule({ database_id: currentDatabaseId, name: name.trim(), trigger_config: trigger, condition_config: conditions, action_config: [action] })
      setName(''); setShowForm(false)
      await load()
    } catch (createError: unknown) {
      setError(getErrorMessage(createError, '自动化规则创建失败'))
    } finally {
      setBusy(false)
    }
  }

  const toggle = async (rule: AutomationRule) => {
    try { await automationApi.toggleRule(rule.id); await load() } catch (toggleError: unknown) { setError(getErrorMessage(toggleError, '规则状态更新失败')) }
  }

  const remove = async (rule: AutomationRule) => {
    if (!window.confirm(`确定删除规则“${rule.name}”吗？`)) return
    try { await automationApi.removeRule(rule.id); await load() } catch (removeError: unknown) { setError(getErrorMessage(removeError, '规则删除失败')) }
  }

  const execute = async (rule: AutomationRule) => {
    if (!currentDatabaseId) return
    setBusy(true); setError('')
    try {
      const response = await patentApi.list({ database_id: currentDatabaseId, page: 1, page_size: 1 })
      const patent = response.items[0]
      if (!patent) throw new Error('当前库没有可执行的专利记录')
      await automationApi.executeRule(rule.id, patent.id)
      await load()
    } catch (executeError: unknown) { setError(getErrorMessage(executeError, '规则执行失败')) } finally { setBusy(false) }
  }

  const runSchedule = async () => {
    setBusy(true); setError('')
    try { await automationApi.scheduleTick(currentDatabaseId); await load() } catch (tickError: unknown) { setError(getErrorMessage(tickError, '定时规则执行失败')) } finally { setBusy(false) }
  }

  return (
    <div className="page-container automation-page">
      <div className="page-header dashboard-header">
        <div><h2 className="page-title">自动化规则</h2><p className="page-subtitle">把重复的字段更新、提醒和导入后处理交给规则。</p></div>
        <div className="dashboard-header-actions"><button className="btn btn-secondary" disabled={busy || !currentDatabaseId} onClick={() => void runSchedule()}>运行定时规则</button><button className="btn btn-primary" onClick={() => setShowForm(value => !value)}>{showForm ? '收起' : '新建规则'}</button></div>
      </div>
      {error && <div className="error-message">{error}</div>}
      {showForm && <div className="automation-form">
        <label>规则名称<input className="form-input" value={name} onChange={event => setName(event.target.value)} placeholder="例如：授权后标记" /></label>
        <label>触发条件<select className="form-input" value={triggerType} onChange={event => setTriggerType(event.target.value as TriggerType)}>{Object.entries(triggerLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        {triggerType === 'field_changed' && <label>监听字段<select className="form-input" value={triggerField} onChange={event => setTriggerField(event.target.value)}>{fields.map(field => <option key={field.key} value={field.key}>{field.name}</option>)}</select></label>}
        {triggerType === 'schedule' && <label>间隔（分钟）<input className="form-input" type="number" min="1" value={scheduleMinutes} onChange={event => setScheduleMinutes(event.target.value)} /></label>}
        <label>附加条件字段<select className="form-input" value={conditionField} onChange={event => setConditionField(event.target.value)}><option value="">不设置</option>{fields.map(field => <option key={field.key} value={field.key}>{field.name}</option>)}</select></label>
        {conditionField && <label>条件值<input className="form-input" value={conditionValue} onChange={event => setConditionValue(event.target.value)} placeholder="等于" /></label>}
        <label>执行动作<select className="form-input" value={actionType} onChange={event => setActionType(event.target.value as ActionType)}><option value="set_field">设置字段</option><option value="send_notification">站内提醒</option></select></label>
        {actionType === 'set_field' ? <><label>目标字段<select className="form-input" value={actionField} onChange={event => setActionField(event.target.value)}>{fields.filter(field => field.editable !== false && field.field_type !== 'formula').map(field => <option key={field.key} value={field.key}>{field.name}</option>)}</select></label><label>目标值<input className="form-input" value={actionValue} onChange={event => setActionValue(event.target.value)} /></label></> : <label>提醒内容<input className="form-input" value={notification} onChange={event => setNotification(event.target.value)} /></label>}
        <button className="btn btn-primary" disabled={busy || !name.trim()} onClick={() => void createRule()}>保存规则</button>
      </div>}
      <div className="automation-list">
        {rules.map(rule => {
          const trigger = rule.trigger_config || {}
          const action = rule.action_config[0] || {}
          return <div className={`automation-rule ${rule.is_enabled ? '' : 'is-disabled'}`} key={rule.id}>
            <div className="automation-rule-main"><div><h3>{rule.name}</h3><p>{triggerLabels[valueText(trigger.type) as TriggerType] || valueText(trigger.type, '未配置')} · {valueText(action.type, '未配置')}</p></div><span className={`rule-status ${rule.is_enabled ? 'enabled' : 'disabled'}`}>{rule.is_enabled ? '已启用' : '已停用'}</span></div>
            <div className="automation-rule-meta"><span>成功 {rule.execution_count}</span><span>失败 {rule.failure_count}</span><span>{rule.last_executed_at ? new Date(rule.last_executed_at).toLocaleString() : '尚未执行'}</span></div>
            <div className="automation-actions"><button className="btn btn-secondary" onClick={() => void toggle(rule)}>{rule.is_enabled ? '停用' : '启用'}</button><button className="btn btn-secondary" disabled={!rule.is_enabled || busy} onClick={() => void execute(rule)}>执行一次</button><button className="btn btn-danger" onClick={() => void remove(rule)}>删除</button></div>
          </div>
        })}
        {rules.length === 0 && <div className="empty-state">当前库还没有自动化规则。</div>}
      </div>
      <section className="automation-log-panel"><div className="section-heading"><h3>执行记录</h3><span>最近 80 条</span></div><div className="automation-log-list">{logs.map(log => <div className="automation-log-row" key={log.id}><span className={`log-status ${log.status}`}>{log.status}</span><span>规则 #{log.rule_id}</span><span>专利 #{log.patent_id ?? '-'}</span><span>{log.error_message || valueText(log.details?.actions, '已处理')}</span><time>{log.executed_at ? new Date(log.executed_at).toLocaleString() : '-'}</time></div>)}{logs.length === 0 && <div className="empty-state">暂无执行记录。</div>}</div></section>
    </div>
  )
}
