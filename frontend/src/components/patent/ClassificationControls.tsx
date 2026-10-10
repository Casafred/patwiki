import { useCallback, useEffect, useRef, useState } from 'react'
import { classificationApi, productApi, tagApi, tagGroupApi } from '../../api'
import type { JsonObject, Product, Tag, TagGroup } from '../../types'
import { getErrorMessage } from '../../lib/errors'
import Icon from '../common/Icon'
import { tagPath } from '../../lib/classifications'

export function ClassificationPicker({ tags, selected, onChange }: { tags: Tag[]; selected: number[]; onChange: (ids: number[]) => void }) {
  const [query, setQuery] = useState('')
  const ordered = tags.map(tag => ({ tag, path: tagPath(tag, tags) })).sort((a, b) => a.path.localeCompare(b.path, 'zh-CN'))
  return <div className="classification-picker">
    <input className="form-input" aria-label="搜索分类" placeholder="搜索分类" value={query} onChange={event => setQuery(event.target.value)} />
    <div className="classification-options">{ordered.filter(item => !query || item.path.toLowerCase().includes(query.toLowerCase())).map(({ tag, path }) =>
      <label key={tag.id}><input type="checkbox" checked={selected.includes(tag.id)} onChange={event => onChange(event.target.checked ? [...selected, tag.id] : selected.filter(id => id !== tag.id))} /><span className="classification-swatch" style={{ background: tag.color || '#64748b' }} /><span>{path}</span></label>)}
      {tags.length === 0 && <div className="empty-state">暂无分类节点</div>}
    </div>
  </div>
}

export function ClassificationCell({ tags, selected, onSave, onCancel }: { tags: Tag[]; selected: number[]; onSave: (ids: number[]) => Promise<void>; onCancel: () => void }) {
  const [ids, setIds] = useState(selected)
  const [busy, setBusy] = useState(false)
  return <div className="classification-cell-editor" onClick={event => event.stopPropagation()}>
    <ClassificationPicker tags={tags} selected={ids} onChange={setIds} />
    <div className="classification-actions"><button className="btn btn-secondary" onClick={onCancel}>取消</button><button className="btn btn-primary" disabled={busy} onClick={async () => { setBusy(true); try { await onSave(ids) } finally { setBusy(false) } }}>保存</button></div>
  </div>
}

export function ClassificationManager({ onChanged }: { onChanged: () => void }) {
  const [groups, setGroups] = useState<TagGroup[]>([])
  const [tags, setTags] = useState<Tag[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [groupId, setGroupId] = useState(0)
  const [exportIds, setExportIds] = useState<number[]>([])
  const [systemName, setSystemName] = useState('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [parentId, setParentId] = useState('')
  const [productId, setProductId] = useState('')
  const [color, setColor] = useState('#0f766e')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const load = useCallback(async () => {
    const [loadedGroups, loadedTags, loadedProducts] = await Promise.all([tagGroupApi.list(), tagApi.list(), productApi.list()])
    setGroups(loadedGroups); setTags(loadedTags); setProducts(loadedProducts)
    setGroupId(current => loadedGroups.some(group => group.id === current) ? current : loadedGroups[0]?.id || 0)
  }, [])
  useEffect(() => { const timer = window.setTimeout(() => { void load().catch(error => setError(getErrorMessage(error))) }, 0); return () => window.clearTimeout(timer) }, [load])
  const execute = async (action: () => Promise<unknown>) => {
    setBusy(true); setError('')
    try { await action(); await load(); onChanged() } catch (error) { setError(getErrorMessage(error)) } finally { setBusy(false) }
  }
  const group = groups.find(item => item.id === groupId)
  const nodes = tags.filter(tag => tag.group_id === groupId)
  const reset = () => { setEditingId(null); setName(''); setParentId(''); setProductId(''); setColor('#0f766e') }
  const blockedParents = new Set<number>(editingId ? [editingId] : [])
  let changed = true
  while (changed) { changed = false; for (const tag of nodes) { if (tag.parent_id && blockedParents.has(tag.parent_id) && !blockedParents.has(tag.id)) { blockedParents.add(tag.id); changed = true } } }
  return <div className="classification-manager">
    {error && <div role="alert" className="management-error">{error}</div>}
    <div className="classification-system-bar"><select className="form-input" aria-label="分类系统" value={groupId} onChange={event => { setGroupId(Number(event.target.value)); reset() }}><option value={0}>选择分类系统</option>{groups.map(group => <option key={group.id} value={group.id}>{group.name}</option>)}</select><input className="form-input" aria-label="新系统名称" placeholder="新系统名称" value={systemName} onChange={event => setSystemName(event.target.value)} /><button className="btn btn-primary" disabled={busy || !systemName.trim()} onClick={() => void execute(async () => { const created = await tagGroupApi.create({ name: systemName.trim() }); setSystemName(''); setGroupId(created.id); reset() })}>新增系统</button></div>
    {group && <>
      <div className="classification-node-form">
        <label>节点名称<input className="form-input" value={name} onChange={event => setName(event.target.value)} /></label>
        <label>父分类<select className="form-input" value={parentId} onChange={event => setParentId(event.target.value)}><option value="">顶层分类</option>{nodes.filter(tag => !blockedParents.has(tag.id)).map(tag => <option key={tag.id} value={tag.id}>{tagPath(tag, tags)}</option>)}</select></label>
        {group.kind === 'product' && <label>关联产品<select className="form-input" value={productId} onChange={event => setProductId(event.target.value)}><option value="">无关联产品</option>{products.map(product => <option key={product.id} value={product.id}>{product.name}</option>)}</select></label>}
        <label>颜色<input type="color" value={color} onChange={event => setColor(event.target.value)} /></label>
        <div className="classification-actions"><button className="btn btn-primary" disabled={busy || !name.trim()} onClick={() => void execute(async () => { const data = { name: name.trim(), group_id: groupId, parent_id: parentId ? Number(parentId) : null, product_id: productId ? Number(productId) : null, color }; if (editingId) await tagApi.update(editingId, data); else await tagApi.create(data); reset() })}>{editingId ? '保存节点' : '新增节点'}</button>{editingId && <button className="btn btn-secondary" onClick={reset}>取消</button>}</div>
      </div>
      <div className="classification-node-list">{nodes.sort((a, b) => tagPath(a, tags).localeCompare(tagPath(b, tags), 'zh-CN')).map(tag => <div key={tag.id}><span className="classification-swatch" style={{ background: tag.color }} /><span>{tagPath(tag, tags)}</span>{tag.product_id && <a href={`/management?product=${tag.product_id}`}>关联产品</a>}<button className="btn btn-secondary" title="编辑节点" onClick={() => { setEditingId(tag.id); setName(tag.name); setParentId(tag.parent_id ? String(tag.parent_id) : ''); setProductId(tag.product_id ? String(tag.product_id) : ''); setColor(tag.color || '#0f766e') }}><Icon name="edit" size={14} /></button><button className="btn btn-secondary" title="删除节点" disabled={busy || !!tag.product_id} onClick={() => { if (window.confirm(`删除分类“${tag.name}”？`)) void execute(() => tagApi.delete(tag.id)) }}><Icon name="trash" size={14} /></button></div>)}</div>
      <div className="classification-actions"><button className="btn btn-secondary" disabled={busy || group.kind === 'product'} onClick={() => { const next = window.prompt('分类系统名称', group.name); if (next?.trim()) void execute(() => tagGroupApi.update(group.id, { name: next.trim() })) }}>重命名系统</button><button className="btn btn-danger" disabled={busy || nodes.length > 0 || group.kind === 'product'} onClick={() => { if (window.confirm(`删除分类系统“${group.name}”？`)) void execute(() => tagGroupApi.delete(group.id)) }}>删除空系统</button></div>
    </>}
    <div className="classification-transfer"><strong>分类配置</strong><div className="classification-export-options">{groups.map(group => <label key={group.id}><input type="checkbox" checked={exportIds.includes(group.id)} onChange={event => setExportIds(event.target.checked ? [...exportIds, group.id] : exportIds.filter(id => id !== group.id))} />{group.name}</label>)}</div><div className="classification-actions">
      <button className="btn btn-secondary" disabled={busy || !exportIds.length} onClick={() => void execute(async () => { const data = await classificationApi.export(exportIds); const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })); const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'patwiki-classifications.json'; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000) })}><Icon name="download" size={14} />导出选定系统</button>
      <button className="btn btn-secondary" disabled={busy} onClick={() => input.current?.click()}><Icon name="file" size={14} />导入配置</button><input ref={input} type="file" accept=".json,application/json" hidden onChange={event => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void execute(async () => { if (file.size > 10 * 1024 * 1024) throw new Error('配置文件不能超过 10 MB'); await classificationApi.import(JSON.parse(await file.text()) as JsonObject) }) }} />
    </div></div>
  </div>
}

export function BulkClassification({ patentIds, onDone, onManage }: { patentIds: number[]; onDone: () => void; onManage: () => void }) {
  const [groups, setGroups] = useState<TagGroup[]>([])
  const [tags, setTags] = useState<Tag[]>([])
  const [groupId, setGroupId] = useState(0)
  const [ids, setIds] = useState<number[]>([])
  const [mode, setMode] = useState<'add' | 'remove' | 'replace'>('add')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { void Promise.all([tagGroupApi.list(), tagApi.list()]).then(([groups, tags]) => { setGroups(groups); setTags(tags); setGroupId(groups[0]?.id || 0) }).catch(error => setError(getErrorMessage(error))) }, [])
  return <div className="classification-bulk">{error && <div role="alert" className="management-error">{error}</div>}<div className="classification-system-bar"><select className="form-input" aria-label="打标分类系统" value={groupId} onChange={event => { setGroupId(Number(event.target.value)); setIds([]) }}><option value={0}>选择分类系统</option>{groups.map(group => <option key={group.id} value={group.id}>{group.name}</option>)}</select><button className="btn btn-secondary" onClick={onManage}>分类系统</button></div><div className="classification-actions" role="group" aria-label="打标模式">{(['add', 'replace', 'remove'] as const).map(item => <label key={item}><input type="radio" name="classification-mode" checked={mode === item} onChange={() => setMode(item)} />{item === 'add' ? '追加' : item === 'replace' ? '替换此系统' : '移除'}</label>)}</div><ClassificationPicker tags={tags.filter(tag => tag.group_id === groupId)} selected={ids} onChange={setIds} /><div className="classification-actions"><button className="btn btn-primary" disabled={busy || !groupId || (!ids.length && mode !== 'replace')} onClick={async () => { setBusy(true); setError(''); try { await classificationApi.apply(patentIds, ids, groupId, mode); onDone() } catch (error) { setError(getErrorMessage(error)) } finally { setBusy(false) } }}>应用到 {patentIds.length} 条专利</button></div></div>
}
