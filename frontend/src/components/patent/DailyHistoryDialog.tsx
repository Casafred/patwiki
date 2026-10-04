import { useMemo, useState } from 'react'
import {
  clearDailyHistory,
  useDailyHistory,
  type DailyHistoryRecord,
} from '../../lib/dailyHistory'
import Icon from '../common/Icon'

interface DailyHistoryDialogProps {
  onClose: () => void
  onOpen: (record: DailyHistoryRecord) => void
}

type HistoryFilter = 'all' | 'viewed' | 'edited'

const FILTERS: { key: HistoryFilter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'viewed', label: '仅浏览' },
  { key: 'edited', label: '仅编辑' },
]

function formatClock(timestamp: number | null | undefined): string {
  if (!timestamp) return '-'
  return new Date(timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function formatDateLabel(): string {
  return new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' })
}

export default function DailyHistoryDialog({ onClose, onOpen }: DailyHistoryDialogProps) {
  const records = useDailyHistory()
  const [filter, setFilter] = useState<HistoryFilter>('all')
  const [keyword, setKeyword] = useState('')

  const filtered = useMemo(() => {
    const text = keyword.trim().toLowerCase()
    return records.filter(record => {
      if (filter === 'edited' && record.editCount === 0) return false
      if (filter === 'viewed' && record.editCount > 0) return false
      if (!text) return true
      return [record.title, record.publicationNumber, record.applicationNumber, record.applicant]
        .some(value => (value || '').toLowerCase().includes(text))
    })
  }, [records, filter, keyword])

  const editedCount = records.filter(record => record.editCount > 0).length

  const handleClear = () => {
    if (!window.confirm('确定要清空今天的浏览与编辑记录吗？清空后无法恢复。')) return
    clearDailyHistory()
  }

  return (
    <div
      role="presentation"
      onMouseDown={event => {
        if (event.target === event.currentTarget) onClose()
      }}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000, display: 'flex',
        justifyContent: 'center', alignItems: 'center', padding: 20,
        background: 'rgba(15, 23, 42, 0.42)',
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="daily-history-title"
        style={{
          width: 'min(760px, 100%)', maxHeight: 'min(760px, 90vh)', display: 'flex', flexDirection: 'column',
          background: '#fff', borderRadius: 10, boxShadow: '0 24px 64px rgba(15, 23, 42, 0.2)', overflow: 'hidden',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, padding: '20px 24px 16px' }}>
          <div>
            <h3 id="daily-history-title" style={{ margin: 0, color: '#0f172a', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Icon name="history" size={18} /> 当日浏览 &amp; 编辑记录
            </h3>
            <div style={{ marginTop: 5, color: '#64748b', fontSize: 12 }}>
              {formatDateLabel()} · 仅保存在本机浏览器 · 共 {records.length} 条，编辑 {editedCount} 条
            </div>
          </div>
          <button className="btn btn-secondary" onClick={onClose} aria-label="关闭当日记录">关闭</button>
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', padding: '0 24px 12px' }}>
          <input
            className="form-input"
            style={{ flex: '1 1 240px' }}
            value={keyword}
            onChange={event => setKeyword(event.target.value)}
            placeholder="搜索标题、公开号、申请号或申请人"
            aria-label="搜索当日记录"
          />
          <div style={{ display: 'flex', gap: 4 }}>
            {FILTERS.map(item => (
              <button
                key={item.key}
                type="button"
                className={`btn btn-sm ${filter === item.key ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setFilter(item.key)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <div style={{ flex: 1, overflow: 'auto', padding: '0 24px' }}>
          {filtered.length === 0 ? (
            <div style={{ padding: '40px 0', textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>
              {records.length === 0 ? '今天还没有浏览或编辑记录' : '没有匹配的记录'}
            </div>
          ) : (
            <div style={{ display: 'grid', gap: 8, paddingBottom: 8 }}>
              {filtered.map(record => (
                <button
                  key={record.patentId}
                  type="button"
                  onClick={() => onOpen(record)}
                  style={{
                    textAlign: 'left', display: 'block', width: '100%', cursor: 'pointer',
                    padding: 12, border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff',
                  }}
                  title="打开该专利详情"
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
                    <span style={{ color: '#0f172a', fontSize: 13, fontWeight: 600, lineHeight: 1.4 }}>
                      {record.title || `专利 #${record.patentId}`}
                    </span>
                    {record.editCount > 0 && (
                      <span style={{
                        flexShrink: 0, color: '#b45309', background: '#fef3c7', border: '1px solid #fde68a',
                        borderRadius: 999, padding: '1px 8px', fontSize: 11, fontWeight: 600,
                      }}>
                        已编辑 {record.editCount} 次
                      </span>
                    )}
                  </div>
                  <div style={{ marginTop: 6, display: 'flex', gap: 14, flexWrap: 'wrap', color: '#64748b', fontSize: 12 }}>
                    {record.publicationNumber && <span>公开号 {record.publicationNumber}</span>}
                    {record.applicationNumber && <span>申请号 {record.applicationNumber}</span>}
                    {record.applicant && <span>{record.applicant}</span>}
                  </div>
                  <div style={{ marginTop: 6, display: 'flex', gap: 14, flexWrap: 'wrap', color: '#94a3b8', fontSize: 11 }}>
                    <span>最近浏览 {formatClock(record.viewedAt)} · 共 {record.viewCount} 次</span>
                    {record.editedAt && <span>最近编辑 {formatClock(record.editedAt)}</span>}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12,
          padding: '12px 24px 18px', borderTop: '1px solid #e2e8f0', color: '#94a3b8', fontSize: 11,
        }}>
          <span>记录按本地自然日保留，次日自动清空</span>
          <button className="btn btn-secondary" onClick={handleClear} disabled={records.length === 0}>清空今日记录</button>
        </div>
      </div>
    </div>
  )
}