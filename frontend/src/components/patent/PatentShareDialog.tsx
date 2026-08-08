import { useCallback, useEffect, useState } from 'react'
import { patentShareApi } from '../../api'
import type { PatentShare } from '../../types'
import { getErrorMessage } from '../../lib/errors'

interface PatentShareDialogProps {
  patentId: number
  onClose: () => void
}

function shareUrl(share: PatentShare): string {
  return `${window.location.origin}${share.share_path}`
}

export default function PatentShareDialog({ patentId, onClose }: PatentShareDialogProps) {
  const [shares, setShares] = useState<PatentShare[]>([])
  const [titleOverride, setTitleOverride] = useState('')
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [copiedToken, setCopiedToken] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadShares = useCallback(async () => {
    setLoading(true)
    try {
      setShares(await patentShareApi.list(patentId))
      setError(null)
    } catch (reason: unknown) {
      setError(getErrorMessage(reason, '加载分享链接失败'))
    } finally {
      setLoading(false)
    }
  }, [patentId])

  useEffect(() => {
    // The callback synchronizes the dialog with the remote share list.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadShares()
  }, [loadShares])

  const copyLink = async (share: PatentShare) => {
    try {
      await navigator.clipboard.writeText(shareUrl(share))
      setCopiedToken(share.token)
      window.setTimeout(() => setCopiedToken(null), 1600)
    } catch (reason: unknown) {
      setError(getErrorMessage(reason, '复制失败，请手动选择链接'))
    }
  }

  const createShare = async () => {
    setCreating(true)
    try {
      const share = await patentShareApi.create(patentId, {
        title_override: titleOverride.trim() || undefined,
      })
      setShares(current => [share, ...current])
      setTitleOverride('')
      await copyLink(share)
    } catch (reason: unknown) {
      setError(getErrorMessage(reason, '创建分享链接失败'))
    } finally {
      setCreating(false)
    }
  }

  const revokeShare = async (share: PatentShare) => {
    if (!window.confirm('确定要撤销这个分享链接吗？撤销后链接将无法访问。')) return
    try {
      await patentShareApi.revoke(patentId, share.token)
      setShares(current => current.map(item => (
        item.token === share.token ? { ...item, is_active: false } : item
      )))
    } catch (reason: unknown) {
      setError(getErrorMessage(reason, '撤销分享链接失败'))
    }
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
      <div role="dialog" aria-modal="true" aria-labelledby="share-dialog-title" style={{
        width: 'min(640px, 100%)', maxHeight: 'min(720px, 90vh)', overflow: 'auto',
        background: '#fff', borderRadius: 10, boxShadow: '0 24px 64px rgba(15, 23, 42, 0.2)',
        padding: 24,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
          <div>
            <h3 id="share-dialog-title" style={{ margin: 0, color: '#0f172a' }}>分享专利主题</h3>
            <div style={{ marginTop: 5, color: '#64748b', fontSize: 12 }}>生成只读 Wiki 页面，适合发给研发或评审同事</div>
          </div>
          <button className="btn btn-secondary" onClick={onClose} aria-label="关闭分享窗口">关闭</button>
        </div>

        <div style={{ marginTop: 20, padding: 14, background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8 }}>
          <label style={{ display: 'block', color: '#475569', fontSize: 12, marginBottom: 6 }} htmlFor="share-title-override">
            页面标题（可选）
          </label>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <input
              id="share-title-override"
              className="form-input"
              style={{ flex: '1 1 300px' }}
              value={titleOverride}
              onChange={event => setTitleOverride(event.target.value)}
              placeholder="默认使用专利标题"
            />
            <button className="btn btn-primary" onClick={() => void createShare()} disabled={creating}>
              {creating ? '生成中...' : '生成链接'}
            </button>
          </div>
        </div>

        {error && (
          <div style={{ marginTop: 12, padding: 10, color: '#991b1b', background: '#fef2f2', borderRadius: 6, fontSize: 12 }}>
            {error}
          </div>
        )}

        <div style={{ marginTop: 20 }}>
          <div style={{ color: '#334155', fontSize: 13, fontWeight: 600, marginBottom: 8 }}>已有链接</div>
          {loading ? (
            <div style={{ color: '#64748b', fontSize: 13 }}>加载中...</div>
          ) : shares.length === 0 ? (
            <div style={{ color: '#94a3b8', fontSize: 13 }}>还没有生成分享链接</div>
          ) : (
            <div style={{ display: 'grid', gap: 8 }}>
              {shares.map(share => (
                <div key={share.token} style={{
                  padding: 12, border: '1px solid #e2e8f0', borderRadius: 8,
                  opacity: share.is_active ? 1 : 0.58,
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
                    <span style={{ color: share.is_active ? '#166534' : '#64748b', fontSize: 12, fontWeight: 600 }}>
                      {share.is_active ? '有效链接' : '已撤销'}
                    </span>
                    <span style={{ color: '#94a3b8', fontSize: 11 }}>访问 {share.access_count} 次</span>
                  </div>
                  <div style={{ marginTop: 6, color: '#475569', fontSize: 12, wordBreak: 'break-all' }}>
                    {shareUrl(share)}
                  </div>
                  {share.is_active && (
                    <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                      <button className="btn btn-secondary" onClick={() => void copyLink(share)}>
                        {copiedToken === share.token ? '已复制' : '复制链接'}
                      </button>
                      <button className="btn btn-secondary" onClick={() => void revokeShare(share)}>撤销</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
