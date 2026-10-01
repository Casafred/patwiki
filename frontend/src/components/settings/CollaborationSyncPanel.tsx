import { useCallback, useEffect, useMemo, useState } from 'react'
import { collaborationSyncApi, databaseApi, productApi } from '../../api'
import type { CollaborationIdentity, CollaborationPackage, PatentDatabase, Product } from '../../types'
import { getErrorMessage } from '../../lib/errors'
import SyncAggregationPanel from './SyncAggregationPanel'

const TOKEN_KEY = 'patwiki_collaboration_token'
const fields = [
  'application_number', 'publication_number', 'grant_number', 'title', 'abstract', 'claims',
  'description_full', 'applicant', 'inventor', 'assignee', 'agent', 'filing_date',
  'publication_date', 'grant_date', 'priority_date', 'priority_number', 'priority_country',
  'country', 'patent_type', 'legal_status', 'legal_status_date', 'legal_status_details',
  'ipc_main', 'ipc_all', 'cpc_main', 'cpc_all', 'category', 'subcategory',
  'technical_problem', 'technical_effect', 'technical_solution', 'has_risk', 'risk_level',
  'risk_description', 'module', 'application_status', 'scope_description', 'notes', 'custom_fields',
]
const fieldNames: Record<string, string> = {
  title: '标题', application_number: '申请号', publication_number: '公开号', grant_number: '授权公告号',
  abstract: '摘要', claims: '权利要求', description_full: '说明书', applicant: '申请人', inventor: '发明人',
  assignee: '当前权利人', agent: '代理机构', filing_date: '申请日', publication_date: '公开日',
  grant_date: '授权日', priority_date: '优先权日', priority_number: '优先权号', priority_country: '优先权国家',
  country: '国家/地区', patent_type: '专利类型', legal_status: '法律状态', legal_status_date: '法律状态日期',
  legal_status_details: '法律状态详情', ipc_main: '主分类号', ipc_all: '全部 IPC', cpc_main: '主 CPC',
  cpc_all: '全部 CPC', category: '品类', subcategory: '子品类', technical_problem: '技术问题',
  technical_effect: '技术效果', technical_solution: '技术方案', has_risk: '风险标记', risk_level: '风险等级',
  risk_description: '风险说明', module: '模块', application_status: '申请状态', scope_description: '保护范围', notes: '备注', custom_fields: '自定义字段',
}
const fieldLabel = (field: string) => fieldNames[field] || field
const panelStyle = { background: '#fff', border: '1px solid #d9e0e8', borderRadius: 6, padding: 16, marginBottom: 16 } as const
const inputStyle = { minWidth: 0, border: '1px solid #cbd5e1', borderRadius: 4, padding: '7px 9px', fontSize: 13 } as const
const buttonStyle = { border: '1px solid #a8bacb', borderRadius: 4, background: '#f8fafc', padding: '7px 10px', cursor: 'pointer', fontSize: 12 } as const

type Unit = { id: number; name: string; team_type?: string | null; unit_type: string }
type Responsibility = Record<string, unknown>
type Grant = { grant_uid: string; username: string; database_id: number; database_name: string; fields: string[]; product_ids: number[]; actions: string[]; expires_at?: string | null; revoked: boolean }
type Account = CollaborationIdentity & { role_assignments?: Array<{ role: string; unit_id?: number | null }> }
type DeviceIdentity = { node_uid: string; name: string; fingerprint: string; public_key: string }
type TrustedDevice = { fingerprint: string; name: string; public_key: string; revoked: boolean; created_at?: string | null }
type ApplyConflict = { entity_uid: string; field_key: string; base_value: unknown; local_value: unknown; remote_value: unknown }
type ApplyPreview = { create_count: number; update_count: number; unchanged_count: number; conflicts: ApplyConflict[] }

export default function CollaborationSyncPanel() {
  const [configured, setConfigured] = useState<boolean | null>(null)
  const [setupPath, setSetupPath] = useState('')
  const [identity, setIdentity] = useState<CollaborationIdentity | null>(null)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [deviceIdentity, setDeviceIdentity] = useState<DeviceIdentity | null>(null)
  const [trustedDevices, setTrustedDevices] = useState<TrustedDevice[]>([])
  const [trustedDeviceName, setTrustedDeviceName] = useState('')
  const [trustedDevicePublicKey, setTrustedDevicePublicKey] = useState('')
  const [units, setUnits] = useState<Unit[]>([])
  const [responsibilities, setResponsibilities] = useState<Responsibility[]>([])
  const [grants, setGrants] = useState<Grant[]>([])
  const [packages, setPackages] = useState<CollaborationPackage[]>([])
  const [databases, setDatabases] = useState<PatentDatabase[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [loginName, setLoginName] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmNewPassword, setConfirmNewPassword] = useState('')
  const [setupToken, setSetupToken] = useState('')
  const [newRole, setNewRole] = useState('member')
  const [newUnit, setNewUnit] = useState('')
  const [targetUser, setTargetUser] = useState('')
  const [targetProduct, setTargetProduct] = useState('')
  const [targetTeam, setTargetTeam] = useState('writing')
  const [targetLevel, setTargetLevel] = useState('owner')
  const [targetUnit, setTargetUnit] = useState('')
  const [grantUser, setGrantUser] = useState('')
  const [grantDatabase, setGrantDatabase] = useState('')
  const [grantProducts, setGrantProducts] = useState<number[]>([])
  const [grantActions, setGrantActions] = useState<string[]>(['export'])
  const [grantEditPassword, setGrantEditPassword] = useState('')
  const [exportDatabaseIds, setExportDatabaseIds] = useState<number[]>([])
  const [exportProducts, setExportProducts] = useState<number[]>([])
  const [exportFields, setExportFields] = useState<string[]>(fields)
  const [exportPreview, setExportPreview] = useState<{ count: number; key: string } | null>(null)
  const [recipients, setRecipients] = useState('')
  const [packagePassword, setPackagePassword] = useState('')
  const [importFile, setImportFile] = useState<File | null>(null)
  const [importPassword, setImportPassword] = useState('')
  const [preview, setPreview] = useState<{ count: number; sample: unknown[]; manifest: Record<string, unknown> } | null>(null)
  const [selectedPackage, setSelectedPackage] = useState('')
  const [selectedRecords, setSelectedRecords] = useState<unknown[]>([])
  const [applyPackageUid, setApplyPackageUid] = useState('')
  const [applyDatabaseId, setApplyDatabaseId] = useState('')
  const [applyEditPassword, setApplyEditPassword] = useState('')
  const [applyPreview, setApplyPreview] = useState<ApplyPreview | null>(null)
  const [applyDecisions, setApplyDecisions] = useState<Record<string, 'local' | 'remote'>>({})

  const isAdmin = useMemo(() => Boolean(identity?.roles.some(role => role === 'system_admin' || role === 'department_leader')), [identity])
  const grantTargetIsViewer = accounts.find(account => String(account.id) === grantUser)?.roles.includes('viewer') || false
  const exportRequest = useMemo(() => ({ database_ids: exportDatabaseIds,
    product_ids: exportProducts.length ? exportProducts : undefined, fields: exportFields,
    recipient_names: recipients.split(',').map(value => value.trim()).filter(Boolean), password: packagePassword }),
  [exportDatabaseIds, exportProducts, exportFields, recipients, packagePassword])
  const exportRequestKey = JSON.stringify(exportRequest)

  const loadReferenceData = useCallback(async () => {
    const [dbs, productRows] = await Promise.all([databaseApi.list(true), productApi.list()])
    setDatabases(dbs.filter(item => !item.is_archived))
    setProducts(productRows.filter(item => item.is_active !== false))
    setExportDatabaseIds(current => current.length ? current : dbs.filter(item => !item.is_archived).slice(0, 1).map(item => item.id))
    setGrantDatabase(current => current || String(dbs.find(item => !item.is_archived)?.id || ''))
    setApplyDatabaseId(current => current || String(dbs.find(item => !item.is_archived)?.id || ''))
  }, [])

  const loadAdminData = useCallback(async () => {
    if (!identity?.roles.some(role => role === 'system_admin' || role === 'department_leader')) return
    const [accountRows, unitRows, responsibilityRows, grantRows] = await Promise.all([
      collaborationSyncApi.accounts(), collaborationSyncApi.units(),
      collaborationSyncApi.responsibilities(), collaborationSyncApi.grants(),
    ])
    setAccounts(accountRows.items)
    setUnits(unitRows)
    setResponsibilities(responsibilityRows.items)
    setGrants(grantRows.items)
    const [localDevice, trustedRows] = await Promise.all([
      collaborationSyncApi.deviceIdentity().catch(error => { setMessage(getErrorMessage(error, '本机设备密钥不可用')); return null }),
      collaborationSyncApi.trustedDevices().catch(error => { setMessage(getErrorMessage(error)); return { items: [] as TrustedDevice[] } }),
    ])
    setDeviceIdentity(localDevice)
    setTrustedDevices(trustedRows.items)
  }, [identity])

  const loadPackages = useCallback(async () => {
    if (!localStorage.getItem(TOKEN_KEY)) return
    const rows = await collaborationSyncApi.listPackages()
    setPackages(rows.items)
  }, [])

  const loadSetup = useCallback(async () => {
    try {
      const status = await collaborationSyncApi.setupStatus()
      setConfigured(status.configured)
      setSetupPath(status.setup_token_path || '')
      const token = localStorage.getItem(TOKEN_KEY)
      if (token) {
        try {
          setIdentity(await collaborationSyncApi.me())
        } catch {
          localStorage.removeItem(TOKEN_KEY)
        }
      }
      await loadReferenceData()
    } catch (error: unknown) {
      setMessage(getErrorMessage(error, '协同服务初始化状态读取失败'))
    }
  }, [loadReferenceData])

  useEffect(() => {
    // Initial status and optional existing session are loaded after mount.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadSetup()
  }, [loadSetup])

  useEffect(() => {
    if (!identity) return
    // These async requests populate the authenticated collaboration view.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void Promise.all([loadAdminData(), loadPackages()]).catch(error => setMessage(getErrorMessage(error)))
  }, [identity, loadAdminData, loadPackages])

  const storeSession = (result: { token: string; user: CollaborationIdentity }) => {
    localStorage.setItem(TOKEN_KEY, result.token)
    setIdentity(result.user)
    setPassword('')
    setMessage(`已登录：${result.user.display_name || result.user.username}`)
  }

  const handleLogin = async () => {
    setBusy(true); setMessage('')
    try { storeSession(await collaborationSyncApi.login({ username: loginName, password })) }
    catch (error: unknown) { setMessage(getErrorMessage(error, '登录失败')) }
    finally { setBusy(false) }
  }

  const handleBootstrap = async () => {
    setBusy(true); setMessage('')
    try {
      const result = await collaborationSyncApi.bootstrap({ username: loginName, display_name: displayName || loginName, password, setup_token: setupToken })
      setConfigured(true); storeSession(result)
    } catch (error: unknown) { setMessage(getErrorMessage(error, '初始化失败')) }
    finally { setBusy(false) }
  }

  const handleLogout = async () => {
    try { await collaborationSyncApi.logout() } catch { /* Expired sessions can still be cleared locally. */ }
    localStorage.removeItem(TOKEN_KEY)
    setIdentity(null)
    setMessage('已退出协同账号')
  }

  const handleChangePassword = async () => {
    if (newPassword.length < 10 || newPassword !== confirmNewPassword) return
    setBusy(true)
    try {
      await collaborationSyncApi.changePassword({ current_password: currentPassword, new_password: newPassword })
      setCurrentPassword(''); setNewPassword(''); setConfirmNewPassword('')
      setMessage('密码已修改，其他登录会话已撤销')
    } catch (error: unknown) { setMessage(getErrorMessage(error, '修改密码失败')) }
    finally { setBusy(false) }
  }

  const handleCreateAccount = async () => {
    setBusy(true)
    try {
      await collaborationSyncApi.createAccount({ username: loginName, display_name: displayName || loginName,
        password, role: newRole, unit_id: newUnit ? Number(newUnit) : undefined })
      setMessage(`协同账号 ${loginName} 已创建`); setLoginName(''); setDisplayName(''); setPassword('')
      await loadAdminData()
    } catch (error: unknown) { setMessage(getErrorMessage(error, '创建账号失败')) }
    finally { setBusy(false) }
  }

  const handleAssign = async () => {
    if (!targetUser || !targetProduct || !targetUnit) return
    setBusy(true)
    try {
      await collaborationSyncApi.assignResponsibility({ user_id: Number(targetUser), product_id: Number(targetProduct),
        team_type: targetTeam, unit_id: Number(targetUnit), level: targetLevel })
      setMessage('品类责任已保存'); await loadAdminData()
    } catch (error: unknown) { setMessage(getErrorMessage(error, '分配品类责任失败')) }
    finally { setBusy(false) }
  }

  const handleCreateGrant = async () => {
    if (!grantUser || !grantDatabase || (grantActions.includes('apply') && grantEditPassword.length < 10)) return
    setBusy(true)
    try {
      await collaborationSyncApi.createGrant({ user_id: Number(grantUser), database_id: Number(grantDatabase),
        product_ids: grantProducts, fields: exportFields, actions: grantActions,
        edit_password: grantActions.includes('apply') ? grantEditPassword : undefined, expires_days: 90 })
      setGrantEditPassword(''); setMessage('同步授权已创建'); await loadAdminData()
    } catch (error: unknown) { setMessage(getErrorMessage(error, '创建授权失败')) }
    finally { setBusy(false) }
  }

  const handleTrustDevice = async () => {
    if (!trustedDeviceName.trim() || !trustedDevicePublicKey.trim()) return
    setBusy(true)
    try {
      const result = await collaborationSyncApi.trustDevice({ name: trustedDeviceName.trim(), public_key: trustedDevicePublicKey.trim() })
      setTrustedDeviceName(''); setTrustedDevicePublicKey('')
      setMessage(`已登记可信设备：${result.name} · ${result.fingerprint}`)
      await loadAdminData()
    } catch (error: unknown) { setMessage(getErrorMessage(error, '登记设备失败')) }
    finally { setBusy(false) }
  }

  const handleRevokeDevice = async (fingerprint: string) => {
    setBusy(true)
    try {
      await collaborationSyncApi.revokeTrustedDevice(fingerprint)
      setMessage(`已撤销设备信任：${fingerprint}`)
      await loadAdminData()
    } catch (error: unknown) { setMessage(getErrorMessage(error, '撤销设备失败')) }
    finally { setBusy(false) }
  }

  const handlePreviewApply = async (packageUid: string) => {
    if (!applyDatabaseId) return
    setBusy(true); setApplyPackageUid(packageUid); setApplyPreview(null); setApplyDecisions({})
    try {
      const result = await collaborationSyncApi.previewApply(packageUid, {
        database_id: Number(applyDatabaseId), edit_password: applyEditPassword || undefined,
      })
      setApplyPreview(result as ApplyPreview)
      setMessage(`主表应用预览：新增 ${result.create_count} 条、更新 ${result.update_count} 条、冲突 ${result.conflicts.length} 项`)
    } catch (error: unknown) { setMessage(getErrorMessage(error, '无法预览主表应用')) }
    finally { setBusy(false) }
  }

  const handleApplyPackage = async () => {
    if (!applyPackageUid || !applyDatabaseId || !applyPreview) return
    setBusy(true)
    try {
      const decisions = applyPreview.conflicts.flatMap(conflict => {
        const choice = applyDecisions[`${conflict.entity_uid}:${conflict.field_key}`]
        return choice ? [{ entity_uid: conflict.entity_uid, field_key: conflict.field_key, choice }] : []
      })
      const result = await collaborationSyncApi.apply(applyPackageUid, {
        database_id: Number(applyDatabaseId), edit_password: applyEditPassword || undefined, decisions,
      })
      setMessage(`主表应用完成：新增 ${result.created} 条、更新 ${result.updated} 条、待处理冲突 ${result.pending_conflicts} 项；同步前备份：${result.backup_path || '未生成（仅内存数据库）'}`)
      setApplyPreview(null); setApplyDecisions({})
      await loadPackages()
    } catch (error: unknown) { setMessage(getErrorMessage(error, '主表应用失败')) }
    finally { setBusy(false) }
  }

  const handlePreviewExport = async () => {
    if (!exportDatabaseIds.length || !recipients.trim() || !packagePassword) return
    setBusy(true); setMessage('')
    try {
      const result = await collaborationSyncApi.previewExport(exportRequest)
      setExportPreview({ count: result.count, key: exportRequestKey })
      setMessage(`范围核对完成：${result.count} 条记录，${result.fields.length} 个字段。确认后才会写入同步包。`)
    } catch (error: unknown) { setExportPreview(null); setMessage(getErrorMessage(error, '无法核对导出范围')) }
    finally { setBusy(false) }
  }

  const handleCreateExport = async () => {
    if (!exportPreview || exportPreview.key !== exportRequestKey) return
    setBusy(true)
    try {
      const generated = await collaborationSyncApi.exportPackage(exportRequest)
      const blob = await collaborationSyncApi.download(generated.package_uid)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = `${generated.package_uid}.pwshare`; anchor.click()
      URL.revokeObjectURL(url)
      setMessage(`同步包已生成：${generated.count} 条记录，SHA-256 ${generated.file_hash}`)
      setExportPreview(null)
      await loadPackages()
    } catch (error: unknown) { setMessage(getErrorMessage(error, '生成同步包失败')) }
    finally { setBusy(false) }
  }

  const handleImportPreview = async () => {
    if (!importFile || !importPassword) return
    setBusy(true); setPreview(null)
    try { setPreview(await collaborationSyncApi.inspect(importFile, importPassword)); setMessage('同步包已解密并通过校验') }
    catch (error: unknown) { setMessage(getErrorMessage(error, '无法读取同步包')) }
    finally { setBusy(false) }
  }

  const handleImport = async () => {
    if (!importFile || !importPassword || !preview) return
    setBusy(true)
    try {
      const result = await collaborationSyncApi.importPackage(importFile, importPassword)
      setMessage(result.status === 'already_processed' ? `该同步包已处理过，跳过重复导入（${result.count} 条记录）` : `已导入 ${result.count} 条只读共享记录`); setPreview(null); setImportFile(null); setImportPassword('')
      await loadPackages()
    } catch (error: unknown) { setMessage(getErrorMessage(error, '导入失败')) }
    finally { setBusy(false) }
  }

  const handleShowRecords = async (packageUid: string) => {
    setSelectedPackage(packageUid)
    try { setSelectedRecords((await collaborationSyncApi.records(packageUid)).items) }
    catch (error: unknown) { setMessage(getErrorMessage(error, '读取共享记录失败')) }
  }

  if (configured === null) return <div style={panelStyle}>正在连接协同服务…</div>

  return <section style={panelStyle} aria-label="部门协同同步">
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, borderBottom: '1px solid #e2e8f0', paddingBottom: 12, marginBottom: 14 }}>
      <div><h3 style={{ margin: 0, fontSize: 15, color: '#1f2937' }}>部门协同与数据同步</h3><div style={{ marginTop: 4, fontSize: 12, color: '#64748b' }}>加密文件交换 · 默认只读 · 本地留存审计记录</div></div>
      {identity && <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}><span style={{ fontSize: 12, color: '#334155' }}>{identity.display_name || identity.username} · {identity.roles.join(', ') || '成员'}</span><button style={buttonStyle} onClick={() => void handleLogout()}>退出</button></div>}
    </div>

    {!identity && <div style={{ display: 'grid', gap: 10, maxWidth: 680 }}>
      {configured ? <><strong style={{ fontSize: 13 }}>协同账号登录</strong>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
          <input style={inputStyle} value={loginName} onChange={event => setLoginName(event.target.value)} placeholder="协同账号" autoComplete="username" />
          <input style={inputStyle} type="password" value={password} onChange={event => setPassword(event.target.value)} placeholder="密码" autoComplete="current-password" />
          <button style={buttonStyle} disabled={busy || !loginName || password.length < 10} onClick={() => void handleLogin()}>登录</button>
        </div>
      </> : <><strong style={{ fontSize: 13 }}>初始化本机协同空间</strong>
        <div style={{ color: '#64748b', fontSize: 12 }}>先从本机协同数据目录读取初始化口令：{setupPath}</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
          <input style={inputStyle} value={setupToken} onChange={event => setSetupToken(event.target.value)} placeholder="初始化口令" />
          <input style={inputStyle} value={loginName} onChange={event => setLoginName(event.target.value)} placeholder="管理员账号" autoComplete="username" />
          <input style={inputStyle} value={displayName} onChange={event => setDisplayName(event.target.value)} placeholder="显示名称" />
          <input style={inputStyle} type="password" value={password} onChange={event => setPassword(event.target.value)} placeholder="管理员密码（至少 10 位）" autoComplete="new-password" />
          <button style={buttonStyle} disabled={busy || !setupToken || !loginName || password.length < 10} onClick={() => void handleBootstrap()}>初始化并登录</button>
        </div>
      </>}
    </div>}

    {identity && <>
      <details style={{ marginBottom: 14 }}>
        <summary style={{ cursor: 'pointer', fontSize: 12, color: '#334155' }}>修改协同密码</summary>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8, maxWidth: 780, paddingTop: 8 }}>
          <input style={inputStyle} type="password" value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} placeholder="当前密码" autoComplete="current-password" />
          <input style={inputStyle} type="password" value={newPassword} onChange={event => setNewPassword(event.target.value)} placeholder="新密码（至少 10 位）" autoComplete="new-password" />
          <input style={inputStyle} type="password" value={confirmNewPassword} onChange={event => setConfirmNewPassword(event.target.value)} placeholder="确认新密码" autoComplete="new-password" />
          <button style={buttonStyle} disabled={busy || currentPassword.length < 10 || newPassword.length < 10 || newPassword !== confirmNewPassword} onClick={() => void handleChangePassword()}>保存新密码</button>
        </div>
      </details>
      {isAdmin && <div style={{ borderTop: '1px solid #e2e8f0', borderBottom: '1px solid #e2e8f0', padding: '10px 0', marginBottom: 14 }}>
        <h4 style={{ margin: '0 0 8px', fontSize: 13 }}>可信同步设备</h4>
        {deviceIdentity && <div style={{ display: 'grid', gap: 6, marginBottom: 10, fontSize: 11 }}>
          <div>本机指纹：<code style={{ overflowWrap: 'anywhere' }}>{deviceIdentity.fingerprint}</code> <button style={buttonStyle} onClick={() => void navigator.clipboard?.writeText(deviceIdentity.fingerprint)}>复制指纹</button></div>
          <div>本机公钥：<code style={{ overflowWrap: 'anywhere' }}>{deviceIdentity.public_key}</code> <button style={buttonStyle} onClick={() => void navigator.clipboard?.writeText(deviceIdentity.public_key)}>复制公钥</button></div>
          <div style={{ color: '#64748b' }}>请通过公司批准的独立渠道核对指纹后，再登记对方公钥。签名证明包来自该设备，不代替员工身份认证。</div>
        </div>}
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(140px, 1fr) minmax(200px, 2fr) auto', gap: 7 }}>
          <input style={inputStyle} value={trustedDeviceName} onChange={event => setTrustedDeviceName(event.target.value)} placeholder="设备名称" />
          <input style={inputStyle} value={trustedDevicePublicKey} onChange={event => setTrustedDevicePublicKey(event.target.value)} placeholder="对方 Ed25519 公钥（Base64）" />
          <button style={buttonStyle} disabled={busy || !trustedDeviceName.trim() || !trustedDevicePublicKey.trim()} onClick={() => void handleTrustDevice()}>登记可信设备</button>
        </div>
        <div style={{ marginTop: 8, maxHeight: 130, overflow: 'auto', fontSize: 11 }}>{trustedDevices.map(device => <div key={device.fingerprint} style={{ display: 'grid', gridTemplateColumns: 'minmax(90px, auto) minmax(0, 1fr) auto', alignItems: 'center', gap: 8, borderTop: '1px solid #edf0f3', padding: '5px 0' }}><span>{device.name} · {device.revoked ? '已撤销' : '有效'}</span><code style={{ overflowWrap: 'anywhere' }}>{device.fingerprint}</code>{!device.revoked && <button style={buttonStyle} disabled={busy} onClick={() => void handleRevokeDevice(device.fingerprint)}>撤销</button>}</div>)}</div>
      </div>}
      {isAdmin && <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 14, marginBottom: 18 }}>
        <div style={{ borderTop: '2px solid #0f766e', paddingTop: 10 }}>
          <h4 style={{ margin: '0 0 8px', fontSize: 13 }}>协同账号</h4>
          <div style={{ display: 'grid', gap: 7 }}>
            <input style={inputStyle} value={loginName} onChange={event => setLoginName(event.target.value)} placeholder="登录账号" />
            <input style={inputStyle} value={displayName} onChange={event => setDisplayName(event.target.value)} placeholder="显示名称" />
            <input style={inputStyle} type="password" value={password} onChange={event => setPassword(event.target.value)} placeholder="初始密码（至少 10 位）" />
            <select style={inputStyle} value={newRole} onChange={event => setNewRole(event.target.value)}>
              <option value="member">组员</option><option value="group_leader">组长</option><option value="department_leader">部门领导</option><option value="system_admin">维护管理员</option><option value="viewer">只读协作者</option>
            </select>
            <select style={inputStyle} value={newUnit} onChange={event => setNewUnit(event.target.value)}><option value="">选择所属组（可选）</option>{units.filter(unit => unit.unit_type === 'team').map(unit => <option key={unit.id} value={unit.id}>{unit.name}</option>)}</select>
            <button style={buttonStyle} disabled={busy || !loginName || password.length < 10 || (newRole === 'group_leader' && !newUnit)} onClick={() => void handleCreateAccount()}>创建账号</button>
          </div>
          <div style={{ marginTop: 8, maxHeight: 170, overflow: 'auto', fontSize: 11, color: '#475569' }}>{accounts.map(account => <div key={account.id} style={{ display: 'grid', gridTemplateColumns: 'minmax(90px, 1fr) minmax(105px, auto) auto', alignItems: 'center', gap: 5, padding: '3px 0' }}><span>{account.display_name || account.username} · {account.username}</span><select style={{ ...inputStyle, padding: '3px 4px', fontSize: 10 }} disabled={!account.active} value={account.roles[0] || 'member'} onChange={event => { const role = event.target.value; const unitId = account.role_assignments?.find(item => item.role === 'group_leader')?.unit_id || (newUnit ? Number(newUnit) : undefined); void collaborationSyncApi.setAccountRole(account.id, role, unitId).then(loadAdminData).catch(error => setMessage(getErrorMessage(error))) }}><option value="member">组员</option><option value="group_leader">组长</option><option value="department_leader">部门领导</option><option value="system_admin">维护管理员</option><option value="viewer">只读协作者</option></select><button style={{ ...buttonStyle, padding: '2px 5px' }} onClick={() => void collaborationSyncApi.setAccountActive(account.id, !account.active).then(loadAdminData).catch(error => setMessage(getErrorMessage(error)))}>{account.active ? '停用' : '启用'}</button></div>)}</div>
          <div style={{ marginTop: 6, color: '#64748b', fontSize: 11 }}>管理员和部门领导拥有本机协同管理权限；组长、组员按品类和字段授权同步；只读协作者不能应用到主表。</div>
        </div>

        <div style={{ borderTop: '2px solid #0f766e', paddingTop: 10 }}>
          <h4 style={{ margin: '0 0 8px', fontSize: 13 }}>品类责任</h4>
          <div style={{ display: 'grid', gap: 7 }}>
            <select style={inputStyle} value={targetUser} onChange={event => setTargetUser(event.target.value)}><option value="">选择同事</option>{accounts.map(account => <option key={account.id} value={account.id}>{account.display_name || account.username} · {account.username}</option>)}</select>
            <select style={inputStyle} value={targetTeam} onChange={event => setTargetTeam(event.target.value)}><option value="writing">撰写组</option><option value="retrieval">检索组</option><option value="analysis">分析组</option></select>
            <select style={inputStyle} value={targetUnit} onChange={event => setTargetUnit(event.target.value)}><option value="">选择小组</option>{units.filter(unit => unit.team_type === targetTeam).map(unit => <option key={unit.id} value={unit.id}>{unit.name}</option>)}</select>
            <select style={inputStyle} value={targetLevel} onChange={event => setTargetLevel(event.target.value)}><option value="owner">主要负责人</option><option value="backup">备份负责人</option><option value="reviewer">复核人（只读协作）</option></select>
            <select style={inputStyle} value={targetProduct} onChange={event => setTargetProduct(event.target.value)}><option value="">选择负责品类</option>{products.map(product => <option key={product.id} value={product.id}>{product.code ? `${product.code} · ` : ''}{product.name}</option>)}</select>
            <button style={buttonStyle} disabled={busy || !targetUser || !targetUnit || !targetProduct} onClick={() => void handleAssign()}>保存品类责任</button>
          </div>
          <div style={{ marginTop: 8, maxHeight: 120, overflow: 'auto', fontSize: 11, color: '#475569' }}>{responsibilities.map((entry, index) => <div key={`${String(entry.id)}-${index}`} style={{ padding: '3px 0' }}>{String(entry.display_name || entry.username)} · {String(entry.product_name)} · {String(entry.team_type)}</div>)}</div>
        </div>

        <div style={{ borderTop: '2px solid #0f766e', paddingTop: 10 }}>
          <h4 style={{ margin: '0 0 8px', fontSize: 13 }}>同步导出授权</h4>
          <div style={{ display: 'grid', gap: 7 }}>
            <select style={inputStyle} value={grantUser} onChange={event => setGrantUser(event.target.value)}><option value="">选择协同账号</option>{accounts.map(account => <option key={account.id} value={account.id}>{account.display_name || account.username}</option>)}</select>
            <select style={inputStyle} value={grantDatabase} onChange={event => setGrantDatabase(event.target.value)}><option value="">选择数据库</option>{databases.map(database => <option key={database.id} value={database.id}>{database.name}</option>)}</select>
            <select multiple style={{ ...inputStyle, height: 96 }} value={grantProducts.map(String)} onChange={event => setGrantProducts(Array.from(event.target.selectedOptions, option => Number(option.value)))}>{products.map(product => <option key={product.id} value={product.id}>{product.name}</option>)}</select>
            <div style={{ fontSize: 11, color: '#64748b' }}>未选择品类表示该库全部品类。字段权限使用导出字段选择。</div>
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 12 }}>
              <label><input type="checkbox" checked={grantActions.includes('export')} onChange={event => setGrantActions(current => event.target.checked ? [...new Set([...current, 'export'])] : current.filter(action => action !== 'export'))} /> 导出</label>
              <label><input type="checkbox" checked={grantActions.includes('apply')} disabled={grantTargetIsViewer} onChange={event => setGrantActions(current => event.target.checked ? [...new Set([...current, 'apply'])] : current.filter(action => action !== 'apply'))} /> 应用到本地主表</label>
            </div>
            {grantTargetIsViewer && <div style={{ fontSize: 11, color: '#9a3412' }}>只读协作者不能获得主表应用权限。</div>}
            {grantActions.includes('apply') && <input style={inputStyle} type="password" value={grantEditPassword} onChange={event => setGrantEditPassword(event.target.value)} placeholder="独立编辑密码（至少 10 位）" />}
            <button style={buttonStyle} disabled={busy || !grantUser || !grantDatabase || !grantActions.length || (grantActions.includes('apply') && grantEditPassword.length < 10)} onClick={() => void handleCreateGrant()}>按当前范围授权 90 天</button>
          </div>
          <div style={{ marginTop: 8, maxHeight: 110, overflow: 'auto', fontSize: 11 }}>{grants.filter(grant => !grant.revoked).map(grant => <div key={grant.grant_uid} style={{ display: 'flex', justifyContent: 'space-between', gap: 6, padding: '3px 0' }}><span>{grant.username} · {grant.database_name} · {grant.actions.join('+')}</span><button style={{ ...buttonStyle, padding: '2px 5px' }} onClick={() => void collaborationSyncApi.revokeGrant(grant.grant_uid).then(loadAdminData).catch(error => setMessage(getErrorMessage(error)))}>撤销</button></div>)}</div>
        </div>
      </div>}

      <div style={{ borderTop: '1px solid #e2e8f0', paddingTop: 14, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 18 }}>
        <div>
          <h4 style={{ margin: '0 0 8px', fontSize: 13 }}>生成加密共享文件</h4>
          <div style={{ display: 'grid', gap: 8 }}>
            <select multiple style={{ ...inputStyle, height: 82 }} value={exportDatabaseIds.map(String)} onChange={event => setExportDatabaseIds(Array.from(event.target.selectedOptions, option => Number(option.value)))}>{databases.map(database => <option key={database.id} value={database.id}>{database.name}</option>)}</select>
            <div style={{ fontSize: 11, color: '#64748b' }}>可选择多个数据库；留出至少一个库后再核对范围。</div>
            <select multiple style={{ ...inputStyle, height: 82 }} value={exportProducts.map(String)} onChange={event => setExportProducts(Array.from(event.target.selectedOptions, option => Number(option.value)))}>{products.map(product => <option key={product.id} value={product.id}>{product.name}</option>)}</select>
            <div style={{ fontSize: 11, color: '#64748b' }}>不选品类时按该库全部记录导出；被授权范围会由服务器再次过滤。</div>
            <details><summary style={{ cursor: 'pointer', fontSize: 12 }}>同步字段（已选 {exportFields.length} 项）</summary><div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(145px, 1fr))', gap: '4px 12px', maxHeight: 180, overflow: 'auto', padding: '8px 0' }}>{fields.map(field => <label key={field} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11 }}><input type="checkbox" checked={exportFields.includes(field)} disabled={field === 'title'} onChange={event => setExportFields(current => event.target.checked ? [...current, field] : current.filter(item => item !== field))} />{fieldLabel(field)}</label>)}</div></details>
            <input style={inputStyle} value={recipients} onChange={event => setRecipients(event.target.value)} placeholder="接收账号，多个账号用逗号分隔" />
            <input style={inputStyle} type="password" value={packagePassword} onChange={event => setPackagePassword(event.target.value)} placeholder="共享密码（至少 10 位，需另行告知接收方）" />
            <button style={{ ...buttonStyle, background: '#edf5f4', borderColor: '#78b9aa' }} disabled={busy || !exportDatabaseIds.length || packagePassword.length < 10 || !recipients.trim()} onClick={() => void handlePreviewExport()}>核对导出范围</button>
            {exportPreview && <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', fontSize: 12, color: '#334155' }}><span>{exportPreview.key === exportRequestKey ? `${exportPreview.count} 条记录待确认` : '导出范围已变更，请重新核对'}</span><button style={buttonStyle} disabled={busy || exportPreview.key !== exportRequestKey} onClick={() => void handleCreateExport()}>确认并生成文件</button></div>}
          </div>
        </div>

        <div>
          <h4 style={{ margin: '0 0 8px', fontSize: 13 }}>接收同步文件</h4>
          <div style={{ display: 'grid', gap: 8 }}>
            <input style={{ ...inputStyle, padding: 5 }} type="file" accept=".pwshare,application/octet-stream" onChange={event => { setImportFile(event.target.files?.[0] || null); setPreview(null) }} />
            <input style={inputStyle} type="password" value={importPassword} onChange={event => setImportPassword(event.target.value)} placeholder="共享密码" />
            <button style={buttonStyle} disabled={busy || !importFile || importPassword.length < 10} onClick={() => void handleImportPreview()}>解密并预览</button>
            {preview && <div style={{ borderTop: '1px solid #e2e8f0', paddingTop: 8, fontSize: 12 }}><div>{preview.count} 条记录 · {String(preview.manifest.created_at || '')} · {String((preview.manifest.created_by as Record<string, unknown> | undefined)?.username || '')} · 签名：{preview.manifest.signature_status === 'trusted' ? '可信' : preview.manifest.signature_status === 'signed_untrusted' ? '待登记信任' : '未签名'}</div>{typeof preview.manifest.signer_fingerprint === 'string' && <div style={{ overflowWrap: 'anywhere', color: '#475569' }}>发送设备指纹：<code>{preview.manifest.signer_fingerprint}</code></div>}<pre style={{ maxHeight: 130, overflow: 'auto', background: '#f8fafc', padding: 8, fontSize: 10 }}>{JSON.stringify(preview.sample, null, 2)}</pre><button style={buttonStyle} disabled={busy} onClick={() => void handleImport()}>导入到只读共享区</button></div>}
          </div>
        </div>
      </div>

      {isAdmin && <SyncAggregationPanel databases={databases} packages={packages} />}
      <div style={{ borderTop: '1px solid #e2e8f0', marginTop: 16, paddingTop: 12 }}>
        <h4 style={{ margin: '0 0 8px', fontSize: 13 }}>同步包收发记录</h4>
        {packages.length === 0 ? <div style={{ fontSize: 12, color: '#64748b' }}>暂无同步包</div> : packages.map((item: CollaborationPackage) => <div key={item.package_uid} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto auto auto', alignItems: 'center', gap: 8, borderTop: '1px solid #edf0f3', padding: '7px 0', fontSize: 11 }}><span style={{ overflowWrap: 'anywhere' }}>{item.direction === 'inbox' ? '收到' : '发出'} · {item.package_uid} · {item.count} 条 · {item.status} · {item.signature_status === 'trusted' || item.signature_status === 'signed' ? '签名' : item.signature_status === 'signed_untrusted' ? '待信任' : '未签名'}</span>{item.direction === 'outbox' && <button style={buttonStyle} onClick={() => void collaborationSyncApi.download(item.package_uid).then(blob => { const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `${item.package_uid}.pwshare`; anchor.click(); URL.revokeObjectURL(url) }).catch(error => setMessage(getErrorMessage(error)))}>下载</button>}{item.direction === 'inbox' && ['imported', 'partially_applied'].includes(item.status) && <button style={buttonStyle} disabled={busy || !databases.length} onClick={() => void handlePreviewApply(item.package_uid)}>预览主表应用</button>}<button style={buttonStyle} onClick={() => void handleShowRecords(item.package_uid)}>查看只读记录</button></div>)}
        {applyPackageUid && <div style={{ display: 'grid', gap: 8, marginTop: 12, borderTop: '1px solid #e2e8f0', paddingTop: 10 }}>
          <strong style={{ fontSize: 12 }}>应用到本地主表 · {applyPackageUid}</strong>
          <select style={inputStyle} value={applyDatabaseId} onChange={event => { setApplyDatabaseId(event.target.value); setApplyPreview(null) }}><option value="">选择本机目标数据库</option>{databases.map(database => <option key={database.id} value={database.id}>{database.name}</option>)}</select>
          {!isAdmin && <input style={inputStyle} type="password" value={applyEditPassword} onChange={event => setApplyEditPassword(event.target.value)} placeholder="编辑授权密码" />}
          <button style={buttonStyle} disabled={busy || !applyDatabaseId} onClick={() => void handlePreviewApply(applyPackageUid)}>重新核对差异</button>
          {applyPreview && <>
            <div style={{ fontSize: 12, color: '#334155' }}>新增 {applyPreview.create_count} 条 · 更新 {applyPreview.update_count} 条 · 无变化 {applyPreview.unchanged_count} 条 · 冲突 {applyPreview.conflicts.length} 项</div>
            {applyPreview.conflicts.map(conflict => {
              const key = `${conflict.entity_uid}:${conflict.field_key}`
              return <div key={key} style={{ borderTop: '1px solid #edf0f3', paddingTop: 7, display: 'grid', gap: 5, fontSize: 11 }}>
                <strong>{conflict.entity_uid} · {fieldLabel(conflict.field_key)}</strong>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 6 }}><div>本机：{JSON.stringify(conflict.local_value)}</div><div>接收：{JSON.stringify(conflict.remote_value)}</div></div>
                <div style={{ display: 'flex', gap: 12 }}><label><input type="radio" name={key} checked={applyDecisions[key] === 'local'} onChange={() => setApplyDecisions(current => ({ ...current, [key]: 'local' }))} /> 保留本机</label><label><input type="radio" name={key} checked={applyDecisions[key] === 'remote'} onChange={() => setApplyDecisions(current => ({ ...current, [key]: 'remote' }))} /> 接受接收值</label></div>
              </div>
            })}
            <button style={{ ...buttonStyle, background: '#edf5f4', borderColor: '#78b9aa' }} disabled={busy} onClick={() => void handleApplyPackage()}>应用无冲突项和已选决策</button>
          </>}
        </div>}
        {selectedPackage && <div style={{ marginTop: 8 }}><div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>{selectedPackage} · 最多显示 1000 条</div><pre style={{ maxHeight: 240, overflow: 'auto', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 4, padding: 10, fontSize: 10 }}>{JSON.stringify(selectedRecords, null, 2)}</pre></div>}
      </div>
    </>}
    {message && <div role="status" style={{ marginTop: 12, borderTop: '1px solid #e2e8f0', paddingTop: 8, fontSize: 12, color: '#334155', overflowWrap: 'anywhere' }}>{message}</div>}
  </section>
}
