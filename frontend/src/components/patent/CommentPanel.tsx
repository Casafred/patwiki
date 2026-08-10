import { useCallback, useEffect, useMemo, useState } from 'react'
import { commentApi } from '../../api'
import type { CommentRecord } from '../../types'
import { getErrorMessage } from '../../lib/errors'

interface CommentPanelProps {
  patentId: number
  onCountChange?: (count: number) => void
}

function formatTime(value?: string | null): string {
  return value ? new Date(value).toLocaleString('zh-CN') : '刚刚'
}

function CommentItem({
  comment,
  replies,
  onReply,
  onResolve,
  onEdit,
  onDelete,
}: {
  comment: CommentRecord
  replies: CommentRecord[]
  onReply: (comment: CommentRecord) => void
  onResolve: (comment: CommentRecord) => void
  onEdit: (comment: CommentRecord) => void
  onDelete: (comment: CommentRecord) => void
}) {
  return (
    <div className={`comment-item ${comment.is_resolved ? 'is-resolved' : ''}`}>
      <div className="comment-item-header">
        <strong>{comment.author_name}</strong>
        {comment.field_key && <span className="comment-field-badge">字段：{comment.field_key}</span>}
        {comment.is_resolved && <span className="comment-resolved-badge">已解决</span>}
        <time>{formatTime(comment.created_at)}</time>
      </div>
      <div className="comment-content">{comment.content}</div>
      {comment.mentions.length > 0 && <div className="comment-mentions">提及：{comment.mentions.map(name => `@${name}`).join(' ')}</div>}
      <div className="comment-item-actions">
        <button type="button" onClick={() => onReply(comment)}>回复</button>
        <button type="button" onClick={() => onEdit(comment)}>编辑</button>
        <button type="button" onClick={() => onResolve(comment)}>{comment.is_resolved ? '恢复' : '解决'}</button>
        <button type="button" className="comment-danger" onClick={() => onDelete(comment)}>删除</button>
      </div>
      {replies.length > 0 && <div className="comment-replies">{replies.map(reply => <CommentItem key={reply.id} comment={reply} replies={[]} onReply={onReply} onResolve={onResolve} onEdit={onEdit} onDelete={onDelete} />)}</div>}
    </div>
  )
}

export default function CommentPanel({ patentId, onCountChange }: CommentPanelProps) {
  const [comments, setComments] = useState<CommentRecord[]>([])
  const [draft, setDraft] = useState('')
  const [authorName, setAuthorName] = useState('当前用户')
  const [replyTo, setReplyTo] = useState<CommentRecord | null>(null)
  const [fieldKey, setFieldKey] = useState('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const loadComments = useCallback(async () => {
    try {
      const loaded = await commentApi.list(patentId)
      setComments(loaded)
      onCountChange?.(loaded.filter(comment => !comment.is_resolved).length)
    } catch (loadError: unknown) {
      setError(getErrorMessage(loadError, '评论加载失败'))
    }
  }, [onCountChange, patentId])

  // Comments are remote collaboration state owned by this panel.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void loadComments() }, [loadComments])

  const repliesByParent = useMemo(() => {
    const groups = new Map<number, CommentRecord[]>()
    comments.forEach(comment => {
      if (comment.parent_id) groups.set(comment.parent_id, [...(groups.get(comment.parent_id) || []), comment])
    })
    return groups
  }, [comments])

  const submit = async () => {
    if (!draft.trim()) return
    setBusy(true); setError('')
    try {
      if (editingId !== null) {
        await commentApi.update(editingId, draft)
      } else {
        await commentApi.create(patentId, {
          content: draft,
          author_name: authorName,
          parent_id: replyTo?.id ?? null,
          field_key: fieldKey.trim() || null,
        })
      }
      setDraft(''); setReplyTo(null); setEditingId(null); setFieldKey('')
      await loadComments()
    } catch (submitError: unknown) {
      setError(getErrorMessage(submitError, '评论保存失败'))
    } finally {
      setBusy(false)
    }
  }

  const resolve = async (comment: CommentRecord) => {
    try { await commentApi.resolve(comment.id, !comment.is_resolved, authorName); await loadComments() } catch (resolveError: unknown) { setError(getErrorMessage(resolveError, '评论状态更新失败')) }
  }

  const edit = (comment: CommentRecord) => {
    setEditingId(comment.id); setDraft(comment.content); setReplyTo(null); setFieldKey(comment.field_key || '')
  }

  const remove = async (comment: CommentRecord) => {
    if (!window.confirm('确定删除这条评论吗？')) return
    try { await commentApi.remove(comment.id); await loadComments() } catch (removeError: unknown) { setError(getErrorMessage(removeError, '评论删除失败')) }
  }

  const topLevel = comments.filter(comment => !comment.parent_id)

  return (
    <div className="comment-panel">
      <div className="comment-panel-header"><div><h3>评论与讨论</h3><p>围绕专利或具体字段留下可追踪的讨论。</p></div><span>{comments.filter(comment => !comment.is_resolved).length} 条待处理</span></div>
      {error && <div className="comment-error">{error}</div>}
      <div className="comment-composer">
        {replyTo && <div className="comment-reply-context">正在回复 {replyTo.author_name}<button type="button" onClick={() => setReplyTo(null)}>取消</button></div>}
        {editingId !== null && <div className="comment-reply-context">正在编辑评论<button type="button" onClick={() => { setEditingId(null); setDraft('') }}>取消</button></div>}
        <div className="comment-composer-row"><input className="form-input" value={authorName} onChange={event => setAuthorName(event.target.value)} placeholder="你的名字" /><input className="form-input" value={fieldKey} onChange={event => setFieldKey(event.target.value)} placeholder="字段标记（可选）" /></div>
        <textarea className="form-input comment-textarea" value={draft} onChange={event => setDraft(event.target.value)} placeholder="写下评论，使用 @用户名 提及协作者..." rows={4} />
        <div className="comment-composer-footer"><span>支持 @提及，评论最多 10000 个字符</span><button className="btn btn-primary" disabled={busy || !draft.trim()} onClick={() => void submit()}>{busy ? '保存中...' : editingId !== null ? '保存修改' : replyTo ? '发布回复' : '发布评论'}</button></div>
      </div>
      <div className="comment-list">
        {topLevel.map(comment => <CommentItem key={comment.id} comment={comment} replies={repliesByParent.get(comment.id) || []} onReply={setReplyTo} onResolve={comment => void resolve(comment)} onEdit={edit} onDelete={comment => void remove(comment)} />)}
        {topLevel.length === 0 && <div className="empty-state">暂无评论，先留下第一条讨论。</div>}
      </div>
    </div>
  )
}
