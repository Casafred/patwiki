import { useCallback, useEffect, useMemo, useState } from 'react'
import { attachmentApi } from '../../api'
import type { AttachmentMeta } from '../../types'
import { getErrorMessage } from '../../lib/errors'

export default function AttachmentLibraryPage() {
  const [items, setItems] = useState<AttachmentMeta[]>([])
  const [query, setQuery] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try { setItems(await attachmentApi.library()) }
    catch (cause: unknown) { setError(getErrorMessage(cause, '附件目录加载失败')) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { void load() }, [load])

  const visible = useMemo(() => {
    const term = query.trim().toLocaleLowerCase()
    if (!term) return items
    return items.filter(item => [item.filename, item.owner_label, item.note, item.file_path].some(value => value?.toLocaleLowerCase().includes(term)))
  }, [items, query])

  const updateNote = async (item: AttachmentMeta) => {
    try {
      if (item.attachment_type === 'project') await attachmentApi.updateProject(item.attachment_id, { note: note.trim() || null })
      else await attachmentApi.update(item.attachment_id, { note: note.trim() || null })
      setEditingId(null)
      await load()
    } catch (cause: unknown) { setError(getErrorMessage(cause, '备注保存失败')) }
  }

  const remove = async (item: AttachmentMeta) => {
    if (!window.confirm(`删除附件“${item.filename}”？`)) return
    try {
      if (item.attachment_type === 'project') await attachmentApi.removeProject(item.attachment_id)
      else await attachmentApi.remove(item.attachment_id)
      await load()
    } catch (cause: unknown) { setError(getErrorMessage(cause, '附件删除失败')) }
  }

  const openFile = async (item: AttachmentMeta, preview: boolean) => {
    const popup = preview ? window.open('', '_blank') : null
    try {
      const blob = item.attachment_type === 'project'
        ? await attachmentApi.downloadProject(item.attachment_id, preview)
        : await attachmentApi.download(item.attachment_id, preview)
      const url = URL.createObjectURL(blob)
      if (popup) {
        popup.location.href = url
        window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
      } else {
        const anchor = document.createElement('a')
        anchor.href = url
        anchor.download = item.filename
        document.body.appendChild(anchor)
        anchor.click()
        anchor.remove()
        window.setTimeout(() => URL.revokeObjectURL(url), 5_000)
      }
    } catch (cause: unknown) {
      popup?.close()
      setError(getErrorMessage(cause, preview ? '附件预览失败' : '附件下载失败'))
    }
  }

  return <section className="attachment-library-page">
    <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'end', gap: 16 }}>
      <div><h2 className="page-title">附件库</h2><p className="page-subtitle">专利附件与项目附件统一索引；原始文件保存在 PatWiki 附件目录。</p></div>
      <input className="form-input" style={{ width: 280 }} placeholder="搜索文件、所属对象或备注" value={query} onChange={event => setQuery(event.target.value)} />
    </div>
    {error && <div role="alert" style={{ color: '#991b1b', padding: 10, background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 6, marginBottom: 12 }}>{error}</div>}
    <div style={{ marginBottom: 10, color: '#64748b', fontSize: 12 }}>{loading ? '正在读取附件目录…' : `共 ${visible.length} 个附件`}</div>
    <div className="attachment-library-list">{visible.map(item => <article className="attachment-library-row" key={`${item.attachment_type}-${item.attachment_id}`}>
      <div className="attachment-library-file"><button type="button" className="attachment-library-file-link" onClick={() => void openFile(item, true)}>{item.filename}</button><span>{item.owner_label || (item.scope === 'project_patent' ? '项目与专利关系说明' : item.attachment_type === 'project' ? '项目资料' : '专利附件')} · {item.mime_type} · {(item.file_size / 1024).toFixed(1)} KB</span>{item.file_path && <small>{item.file_path}</small>}{editingId === item.id ? <div className="attachment-library-note-edit"><input className="form-input" value={note} onChange={event => setNote(event.target.value)} /><button className="btn btn-secondary" onClick={() => void updateNote(item)}>保存</button><button className="btn btn-ghost" onClick={() => setEditingId(null)}>取消</button></div> : <small>备注：{item.note || '无'}</small>}</div>
      <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}><button className="btn btn-secondary" onClick={() => void openFile(item, true)}>预览</button><button className="btn btn-secondary" onClick={() => void openFile(item, false)}>下载</button><button className="btn btn-secondary" onClick={() => { setEditingId(item.id); setNote(item.note || '') }}>备注</button><button className="btn btn-danger" onClick={() => void remove(item)}>删除</button></div>
    </article>)}{!loading && visible.length === 0 && <div style={{ padding: 48, textAlign: 'center', color: '#94a3b8' }}>没有匹配的附件</div>}</div>
  </section>
}
