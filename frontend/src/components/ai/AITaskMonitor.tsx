import { useState, useEffect, useCallback } from 'react'
import { aiApi } from '../../api'
import type { AITask, AITaskRequestSample, AITaskResponseSample, CustomField } from '../../types'
import { getErrorMessage } from '../../lib/errors'

export default function AITaskMonitor() {
  const [tasks, setTasks] = useState<AITask[]>([])
  const [aiFields, setAiFields] = useState<CustomField[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('')
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [now, setNow] = useState(() => Date.now())

  const hasRunning = tasks.some(t => t.status === 'pending' || t.status === 'processing' || t.status === 'running')

  const loadTasks = useCallback(async () => {
    try {
      const params: { status?: string } = {}
      if (statusFilter) params.status = statusFilter
      const data = await aiApi.listTasks(params)
      setTasks(data)
    } catch (e) {
      console.error('Failed to load AI tasks:', e)
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => {
    // The request updates component state asynchronously after the effect runs.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadTasks()
    void aiApi.listAIFields().then(setAiFields).catch(error => console.error('Failed to load AI fields:', error))
  }, [loadTasks])

  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(interval)
  }, [])

  // 自动刷新（有运行中任务时每 2 秒刷新一次）
  useEffect(() => {
    if (!autoRefresh) return
    const interval = setInterval(() => {
      if (hasRunning || statusFilter === '') {
        loadTasks()
      }
    }, hasRunning ? 2000 : 10000)
    return () => clearInterval(interval)
  }, [autoRefresh, hasRunning, statusFilter, loadTasks])

  const handleDelete = async (id: number) => {
    if (!confirm('确定要删除此任务记录吗？')) return
    try {
      await aiApi.deleteTask(id)
      loadTasks()
    } catch (error: unknown) {
      alert('删除失败: ' + getErrorMessage(error))
    }
  }

  const getStatusBadge = (status: string) => {
    const map: Record<string, { label: string; bg: string; color: string }> = {
      pending: { label: '等待中', bg: '#fef3c7', color: '#92400e' },
      processing: { label: '处理中', bg: '#dbeafe', color: '#1e40af' },
      running: { label: '运行中', bg: '#dbeafe', color: '#1e40af' },
      completed: { label: '已完成', bg: '#dcfce7', color: '#166534' },
      completed_with_errors: { label: '部分成功', bg: '#fef3c7', color: '#92400e' },
      failed: { label: '失败', bg: '#fee2e2', color: '#991b1b' },
    }
    const s = map[status] || { label: status, bg: '#f1f5f9', color: '#475569' }
    return (
      <span style={{
        padding: '3px 10px',
        borderRadius: 12,
        fontSize: 11,
        fontWeight: 500,
        background: s.bg,
        color: s.color,
      }}>
        {s.label}
      </span>
    )
  }

  const getFieldName = (key?: string) => {
    if (!key) return '-'
    const field = aiFields.find(f => f.key === key)
    return field ? field.name : key
  }

  const getProgress = (task: AITask) => {
    if (task.total_items === 0) return 0
    return Math.round((task.processed_items / task.total_items) * 100)
  }

  const formatTime = (time?: string) => {
    if (!time) return '-'
    return new Date(time).toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }

  const getDuration = (task: AITask) => {
    if (!task.started_at) return '-'
    const start = new Date(task.started_at).getTime()
    const end = task.completed_at ? new Date(task.completed_at).getTime() : now
    const sec = Math.floor((end - start) / 1000)
    if (sec < 60) return `${sec}秒`
    return `${Math.floor(sec / 60)}分${sec % 60}秒`
  }

  return (
    <div>
      <div className="page-header">
        <h2 className="page-title">AI 任务监控</h2>
        <p className="page-subtitle">
          查看 AI 字段抽取任务进度
        </p>
      </div>

      <div className="toolbar">
        <select
          className="form-input"
          style={{ maxWidth: 150 }}
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setLoading(true) }}
        >
          <option value="">全部状态</option>
          <option value="pending">等待中</option>
          <option value="processing">处理中</option>
          <option value="completed">已完成</option>
          <option value="completed_with_errors">部分成功</option>
          <option value="failed">失败</option>
        </select>

        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#475569' }}>
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
          />
          自动刷新 {hasRunning && <span style={{ color: '#2563eb' }}>(2s)</span>}
        </label>

        <button className="btn btn-secondary" onClick={loadTasks} style={{ marginLeft: 'auto' }}>
          刷新
        </button>
      </div>

      {loading ? (
        <div className="loading-spinner">
          <div className="spinner"></div>
          加载中...
        </div>
      ) : tasks.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">[AI]</div>
          <div className="empty-state-title">暂无 AI 任务</div>
          <div className="empty-state-desc">
            在专利列表中选中专利后点击"AI批量处理"按钮，或在专利详情页的"AI 分析"Tab 中点击"生成"按钮，即可启动 AI 任务。
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {tasks.map(task => {
            const progress = getProgress(task)
            const isRunning = task.status === 'pending' || task.status === 'processing' || task.status === 'running'
            return (
              <div
                key={task.id}
                style={{
                  background: 'white',
                  border: '1px solid #e2e8f0',
                  borderRadius: 8,
                  padding: 16,
                }}
              >
                {/* 任务头部 */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>
                    #{task.id} · {getFieldName(task.field_key)}
                  </div>
                  {getStatusBadge(task.status)}
                  {task.model_name && (
                    <span style={{ fontSize: 11, color: '#94a3b8' }}>模型: {task.model_name}</span>
                  )}
                  <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                    {!isRunning && (
                      <button
                        className="btn btn-secondary"
                        style={{ fontSize: 12, padding: '4px 10px' }}
                        onClick={() => handleDelete(task.id)}
                      >
                        删除
                      </button>
                    )}
                  </div>
                </div>

                {/* 进度条 */}
                <div style={{ marginBottom: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#64748b', marginBottom: 4 }}>
                    <span>
                      进度: {task.processed_items} / {task.total_items}
                      {task.success_count > 0 && <span style={{ color: '#16a34a', marginLeft: 8 }}>✓ {task.success_count}</span>}
                      {task.failed_count > 0 && <span style={{ color: '#dc2626', marginLeft: 8 }}>✗ {task.failed_count}</span>}
                    </span>
                    <span>{progress}%</span>
                  </div>
                  <div style={{ height: 6, background: '#f1f5f9', borderRadius: 3, overflow: 'hidden' }}>
                    <div
                      style={{
                        height: '100%',
                        width: `${progress}%`,
                        background: task.status === 'failed' ? '#dc2626' :
                                   task.status === 'completed_with_errors' ? '#f59e0b' :
                                   task.status === 'completed' ? '#16a34a' : '#2563eb',
                        transition: 'width 0.3s',
                      }}
                    />
                  </div>
                </div>

                {/* 时间信息 */}
                <div style={{ display: 'flex', gap: 16, fontSize: 11, color: '#94a3b8' }}>
                  <span>创建: {formatTime(task.created_at)}</span>
                  {task.started_at && <span>开始: {formatTime(task.started_at)}</span>}
                  {task.completed_at && <span>完成: {formatTime(task.completed_at)}</span>}
                  {task.started_at && <span>耗时: {getDuration(task)}</span>}
                </div>

                {/* 错误详情 */}
                {task.errors && Array.isArray(task.errors) && task.errors.length > 0 && (
                  <details style={{ marginTop: 8 }}>
                    <summary style={{ cursor: 'pointer', fontSize: 12, color: '#dc2626' }}>
                      错误详情 ({task.errors.length})
                    </summary>
                    <div style={{
                      marginTop: 8,
                      padding: 8,
                      background: '#fef2f2',
                      borderRadius: 4,
                      fontSize: 11,
                      color: '#991b1b',
                      maxHeight: 150,
                      overflow: 'auto',
                    }}>
                      {task.errors.slice(0, 10).map((err, i) => (
                        <div key={i} style={{ marginBottom: 4 }}>
                          {err.patent_id ? `专利 #${err.patent_id}：` : ''}
                          {err.stage ? `[${err.stage}] ` : ''}
                          {err.error || '未知错误'}
                        </div>
                      ))}
                      {task.errors.length > 10 && (
                        <div style={{ color: '#64748b', marginTop: 4 }}>...共 {task.errors.length} 条错误</div>
                      )}
                    </div>
                  </details>
                )}

                {/* P0-15：请求内容样本 */}
                {task.request_content && Array.isArray(task.request_content) && task.request_content.length > 0 && (
                  <details style={{ marginTop: 8 }}>
                    <summary style={{ cursor: 'pointer', fontSize: 12, color: '#2563eb' }}>
                      请求内容样本 ({task.request_content.length})
                    </summary>
                    <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {task.request_content.slice(0, 5).map((sample: AITaskRequestSample, i: number) => (
                        <div
                          key={i}
                          style={{
                            padding: 8,
                            background: '#f8fafc',
                            border: '1px solid #e2e8f0',
                            borderRadius: 4,
                            fontSize: 11,
                          }}
                        >
                          <div style={{ color: '#64748b', marginBottom: 4 }}>
                            专利 #{sample.patent_id ?? '-'}
                          </div>
                          <pre style={{
                            margin: 0,
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word',
                            color: '#1e293b',
                            maxHeight: 200,
                            overflow: 'auto',
                            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                          }}>
                            {sample.prompt || '(空)'}
                          </pre>
                        </div>
                      ))}
                      {task.request_content.length > 5 && (
                        <div style={{ color: '#94a3b8', fontSize: 11 }}>...共 {task.request_content.length} 条样本</div>
                      )}
                    </div>
                  </details>
                )}

                {/* P0-15：返回内容样本 */}
                {task.response_content && Array.isArray(task.response_content) && task.response_content.length > 0 && (
                  <details style={{ marginTop: 8 }}>
                    <summary style={{ cursor: 'pointer', fontSize: 12, color: '#16a34a' }}>
                      返回内容样本 ({task.response_content.length})
                    </summary>
                    <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {task.response_content.slice(0, 5).map((sample: AITaskResponseSample, i: number) => (
                        <div
                          key={i}
                          style={{
                            padding: 8,
                            background: '#f0fdf4',
                            border: '1px solid #bbf7d0',
                            borderRadius: 4,
                            fontSize: 11,
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                            <span style={{ color: '#64748b' }}>专利 #{sample.patent_id ?? '-'}</span>
                            {sample.model && (
                              <span style={{ color: '#94a3b8' }}>实际模型: {sample.model}</span>
                            )}
                          </div>
                          <pre style={{
                            margin: 0,
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word',
                            color: '#166534',
                            maxHeight: 200,
                            overflow: 'auto',
                            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                          }}>
                            {sample.response || '(空)'}
                          </pre>
                        </div>
                      ))}
                      {task.response_content.length > 5 && (
                        <div style={{ color: '#94a3b8', fontSize: 11 }}>...共 {task.response_content.length} 条样本</div>
                      )}
                    </div>
                  </details>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
