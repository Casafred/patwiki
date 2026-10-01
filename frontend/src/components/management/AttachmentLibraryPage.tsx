import { useCallback, useEffect, useMemo, useState } from 'react'
import { attachmentApi } from '../../api'
import type { AttachmentMeta } from '../../types'
import { getErrorMessage } from '../../lib/errors'
import { save as saveDesktopFile } from '@tauri-apps/plugin-dialog'
import { writeFile as writeDesktopFile } from '@tauri-apps/plugin-fs'

export default function AttachmentLibraryPage() {
  const [items, setItems] = useState<AttachmentMeta[]>([])
  const [query, setQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')
  const [ownerFilter, setOwnerFilter] = useState('all')
  const [showTrash, setShowTrash] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [sortBy, setSortBy] = useState<'time_desc' | 'time_asc' | 'name'>('time_desc')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [preview, setPreview] = useState<{ url: string; filename: string; mimeType: string } | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try { setItems(await (showTrash ? attachmentApi.trash() : attachmentApi.library())) }
    catch (cause: unknown) { setError(getErrorMessage(cause, '附件目录加载失败')) }
    finally { setLoading(false) }
  }, [showTrash])

  useEffect(() => { void load() }, [load])

  const visible = useMemo(() => {
    const term = query.trim().toLocaleLowerCase()
    if (!term) return items
    return items.filter(item => (typeFilter === 'all' || (item.mime_type || '').split('/')[0] === typeFilter) && (ownerFilter === 'all' || item.attachment_type === ownerFilter) && (!term || [item.filename, item.owner_label, item.note, item.file_path].some(value => value?.toLocaleLowerCase().includes(term)))).sort((a, b) => sortBy === 'name' ? a.filename.localeCompare(b.filename) : sortBy === 'time_asc' ? (a.uploaded_at || '').localeCompare(b.uploaded_at || '') : (b.uploaded_at || '').localeCompare(a.uploaded_at || ''))
  }, [items, query, typeFilter, ownerFilter, sortBy])

  const typeCounts = useMemo(() => items.reduce<Record<string, number>>((result, item) => {
    const type = (item.mime_type || 'other').split('/')[0]
    result[type] = (result[type] || 0) + 1
    return result
  }, {}), [items])
  const groups = useMemo(() => Object.entries(visible.reduce<Record<string, AttachmentMeta[]>>((result, item) => {
    const type = (item.mime_type || 'other').split('/')[0]
    ;(result[type] ||= []).push(item)
    return result
  }, {})).sort(([left], [right]) => left.localeCompare(right)), [visible])

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

  const bulkDelete = async () => {
    if (!selected.size || !window.confirm(`确认将选中的 ${selected.size} 个附件移入回收站？`)) return
    try {
      const chosen = items.filter(item => selected.has(item.id)).map(item => ({ attachment_type: item.attachment_type, attachment_id: item.attachment_id }))
      await attachmentApi.bulkDelete(chosen)
      setSelected(new Set())
      await load()
    } catch (cause) { setError(getErrorMessage(cause, '批量删除失败')) }
  }

  const restoreSelected = async () => {
    try {
      const chosen = items.filter(item => selected.has(item.id)).map(item => ({ attachment_type: item.attachment_type, attachment_id: item.attachment_id }))
      await attachmentApi.restore(chosen)
      setSelected(new Set())
      await load()
    } catch (cause) { setError(getErrorMessage(cause, '恢复附件失败')) }
  }

  const openFile = async (item: AttachmentMeta, shouldPreview: boolean) => {
    try {
      const blob = item.attachment_type === 'project'
        ? await attachmentApi.downloadProject(item.attachment_id, shouldPreview)
        : await attachmentApi.download(item.attachment_id, shouldPreview)
      if (!(blob instanceof Blob) || blob.size === 0) throw new Error('附件内容为空')
      if (shouldPreview) {
        setPreview({ url: URL.createObjectURL(blob), filename: item.filename, mimeType: item.mime_type })
        return
      }
      if ('__TAURI_INTERNALS__' in window) {
        const path = await saveDesktopFile({ defaultPath: item.filename, filters: [{ name: item.mime_type, extensions: [item.filename.split('.').pop() || 'bin'] }] })
        if (path) await writeDesktopFile(path, new Uint8Array(await blob.arrayBuffer()))
        return
      }
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = item.filename
      anchor.style.display = 'none'
      document.body.appendChild(anchor)
      anchor.click()
      window.setTimeout(() => { URL.revokeObjectURL(url); anchor.remove() }, 2000)
    } catch (cause: unknown) {
      setError(getErrorMessage(cause, shouldPreview ? '附件预览失败' : '附件下载失败'))
    }
  }

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview.url) }, [preview])

  return <section className="attachment-library-page">
    <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'end', gap: 16 }}>
      <div><h2 className="page-title">附件库</h2><p className="page-subtitle">按文件类型、所属对象和来源集中管理附件。</p></div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}><input className="form-input" style={{ width: 280 }} placeholder="搜索文件、所属对象或备注" value={query} onChange={event => setQuery(event.target.value)} /><button className="btn btn-secondary" onClick={() => { setShowTrash(value => !value); setSelected(new Set()) }}>{showTrash ? '返回附件库' : '打开回收站'}</button></div>
    </div>
    <div className="attachment-library-toolbar">
      <div style={{ display: 'flex', gap: 8 }}><button className="btn btn-secondary" disabled={!selected.size || showTrash} onClick={() => void bulkDelete()}>批量移入回收站 ({selected.size})</button>{showTrash && <button className="btn btn-primary" disabled={!selected.size} onClick={() => void restoreSelected()}>恢复选中 ({selected.size})</button>}</div>
      <div className="attachment-library-filters"><select className="form-input" value={typeFilter} onChange={event => setTypeFilter(event.target.value)}><option value="all">全部类型</option><option value="image">图片</option><option value="application">文档</option><option value="text">文本</option></select><select className="form-input" value={ownerFilter} onChange={event => setOwnerFilter(event.target.value)}><option value="all">全部归属</option><option value="patent">专利附件</option><option value="project">项目附件</option></select><select className="form-input" value={sortBy} onChange={event => setSortBy(event.target.value as typeof sortBy)}><option value="time_desc">最新上传</option><option value="time_asc">最早上传</option><option value="name">文件名</option></select></div>
      <div className="attachment-library-type-summary">{Object.entries(typeCounts).map(([type, count]) => <button type="button" key={type} className={typeFilter === type ? 'is-active' : ''} onClick={() => setTypeFilter(type)}>{type === 'image' ? '图片' : type === 'application' ? '文档' : type === 'text' ? '文本' : '其他'} <strong>{count}</strong></button>)}</div>
    </div>
    {error && <div role="alert" style={{ color: '#991b1b', padding: 10, background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 6, marginBottom: 12 }}>{error}</div>}
    <div style={{ marginBottom: 10, color: '#64748b', fontSize: 12 }}>{loading ? '正在读取附件目录…' : `共 ${visible.length} 个附件`}</div>
    <div className="attachment-library-list">{groups.map(([type, group]) => <div className="attachment-library-group" key={type}><h3>{type === 'image' ? '图片' : type === 'application' ? '文档' : type === 'text' ? '文本' : '其他'} <span>{group.length}</span></h3>{group.map(item => <article className="attachment-library-row" key={`${item.attachment_type}-${item.attachment_id}`}>
      <input type="checkbox" checked={selected.has(item.id)} onChange={event => setSelected(previous => { const next = new Set(previous); if (event.target.checked) next.add(item.id); else next.delete(item.id); return next })} />
      <div className="attachment-library-file"><button type="button" className="attachment-library-file-link" onClick={() => void openFile(item, true)}>{item.filename}</button><span>{item.owner_label || (item.scope === 'project_patent' ? '项目与专利关系说明' : item.attachment_type === 'project' ? '项目资料' : '专利附件')} · {item.mime_type} · {(item.file_size / 1024).toFixed(1)} KB</span>{item.file_path && <small>{item.file_path}</small>}{editingId === item.id ? <div className="attachment-library-note-edit"><input className="form-input" value={note} onChange={event => setNote(event.target.value)} /><button className="btn btn-secondary" onClick={() => void updateNote(item)}>保存</button><button className="btn btn-ghost" onClick={() => setEditingId(null)}>取消</button></div> : <small>备注：{item.note || '无'}</small>}</div>
      <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>{!showTrash && <><button className="btn btn-secondary" onClick={() => void openFile(item, true)}>预览</button><button className="btn btn-secondary" onClick={() => void openFile(item, false)}>下载</button><button className="btn btn-secondary" onClick={() => { setEditingId(item.id); setNote(item.note || '') }}>备注</button><button className="btn btn-danger" onClick={() => void remove(item)}>删除</button></>}</div>
    </article>)}</div>)}{!loading && visible.length === 0 && <div style={{ padding: 48, textAlign: 'center', color: '#94a3b8' }}>没有匹配的附件</div>}</div>
    {preview && <div className="attachment-preview-overlay" role="dialog" aria-modal="true" onMouseDown={event => { if (event.target === event.currentTarget) setPreview(null) }}>
      <div className="attachment-preview-dialog">
        <div className="attachment-preview-header"><strong>{preview.filename}</strong><button type="button" className="btn btn-ghost" onClick={() => setPreview(null)}>关闭</button></div>
        {preview.mimeType.startsWith('image/') ? <img src={preview.url} alt={preview.filename} className="attachment-preview-content" /> : <iframe title={preview.filename} src={preview.url} className="attachment-preview-content" />}
      </div>
    </div>}
  </section>
}
