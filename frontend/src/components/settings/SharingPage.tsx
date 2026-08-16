import { useState, useEffect, useCallback } from 'react'
import { sharingApi, databaseApi, departmentApi, productLineApi } from '../../api'
import { useAppStore } from '../../store'
import type { User, DatabaseMember, Department } from '../../types'
import { getErrorMessage } from '../../lib/errors'

export default function SharingPage() {
  const { currentUser, setCurrentUser, databases, currentDatabaseId } = useAppStore()
  const [users, setUsers] = useState<User[]>([])
  const [members, setMembers] = useState<DatabaseMember[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [productLines, setProductLines] = useState<Array<{ id: number; name: string; code?: string; department_id?: number | null }>>([])
  const [selectedDbId, setSelectedDbId] = useState<number | null>(currentDatabaseId)

  // 新建用户
  const [showCreateUser, setShowCreateUser] = useState(false)
  const [newUsername, setNewUsername] = useState('')
  const [newEmployeeNo, setNewEmployeeNo] = useState('')
  const [newDisplayName, setNewDisplayName] = useState('')
  const [newUserRole, setNewUserRole] = useState<'admin' | 'member'>('member')
  const [newUserDeptId, setNewUserDeptId] = useState<string>('')
  const [newUserGroupId, setNewUserGroupId] = useState<string>('')
  const [newUserProductLineId, setNewUserProductLineId] = useState<string>('')
  const [newUserOrgRole, setNewUserOrgRole] = useState('')

  // 编辑用户角色/部门
  const [editingUserId, setEditingUserId] = useState<number | null>(null)
  const [editDeptId, setEditDeptId] = useState<string>('')
  const [editEmployeeNo, setEditEmployeeNo] = useState('')
  const [editGroupId, setEditGroupId] = useState<string>('')
  const [editProductLineId, setEditProductLineId] = useState<string>('')
  const [editOrgRole, setEditOrgRole] = useState('')

  // 添加成员
  const [showAddMember, setShowAddMember] = useState(false)
  const [addMemberUsername, setAddMemberUsername] = useState('')
  const [addMemberRole, setAddMemberRole] = useState<'editor' | 'viewer'>('viewer')

  const loadUsers = useCallback(async () => {
    try {
      const list = await sharingApi.listUsers()
      setUsers(list)
    } catch (error: unknown) {
      console.error('Failed to load users:', error)
    }
  }, [])

  const loadDepartments = useCallback(async () => {
    try {
      const list = await departmentApi.list()
      setDepartments(list)
    } catch (error: unknown) {
      console.error('Failed to load departments:', error)
    }
  }, [])

  const loadProductLines = useCallback(async () => {
    try {
      setProductLines(await productLineApi.list())
    } catch (error: unknown) {
      console.error('Failed to load product lines:', error)
    }
  }, [])

  const loadMembers = useCallback(async () => {
    if (!selectedDbId) { setMembers([]); return }
    try {
      const list = await sharingApi.listMembers(selectedDbId)
      setMembers(list)
    } catch (e) {
      console.error('Failed to load members:', e)
    }
  }, [selectedDbId])

  useEffect(() => {
    // The request updates state asynchronously after the effect starts.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadUsers()
  }, [loadUsers])

  useEffect(() => {
    // Department data is synchronized from the management API.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadDepartments()
  }, [loadDepartments])

  useEffect(() => {
    // Product-line data is synchronized from the management API.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadProductLines()
  }, [loadProductLines])

  useEffect(() => {
    // The request updates state asynchronously after the effect starts.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadMembers()
  }, [loadMembers])

  const handleCreateUser = async () => {
    if (!newUsername.trim()) return
    try {
      const user = await sharingApi.createUser({
        username: newUsername.trim(),
        display_name: newDisplayName.trim() || undefined,
        role: newUserRole,
        employee_no: newEmployeeNo.trim() || undefined,
        department_id: newUserDeptId ? Number(newUserDeptId) : undefined,
        group_id: newUserGroupId ? Number(newUserGroupId) : undefined,
        product_line_id: newUserProductLineId ? Number(newUserProductLineId) : undefined,
        organization_role: newUserOrgRole.trim() || undefined,
      })
      setUsers(prev => [...prev, user])
      setNewUsername('')
      setNewEmployeeNo('')
      setNewDisplayName('')
      setNewUserRole('member')
      setNewUserDeptId('')
      setNewUserGroupId('')
      setNewUserProductLineId('')
      setNewUserOrgRole('')
      setShowCreateUser(false)
    } catch (error: unknown) {
      alert(getErrorMessage(error, '创建用户失败'))
    }
  }

  const handleUpdateUser = async (userId: number) => {
    try {
      const updated = await sharingApi.updateUser(userId, {
        employee_no: editEmployeeNo.trim() || null,
        department_id: editDeptId ? Number(editDeptId) : null,
        group_id: editGroupId ? Number(editGroupId) : null,
        product_line_id: editProductLineId ? Number(editProductLineId) : null,
        organization_role: editOrgRole.trim() || null,
      })
      setUsers(prev => prev.map(u => u.id === updated.id ? updated : u))
      setEditingUserId(null)
    } catch (error: unknown) {
      alert(getErrorMessage(error, '更新用户部门失败'))
    }
  }

  const handleUpdateUserRole = async (userId: number, role: 'admin' | 'member') => {
    try {
      const updated = await sharingApi.updateUser(userId, { role })
      setUsers(prev => prev.map(u => u.id === updated.id ? updated : u))
    } catch (error: unknown) {
      alert(getErrorMessage(error, '更新用户角色失败'))
    }
  }

  const handleSelectUser = async (user: User) => {
    setCurrentUser(user)
  }

  const handleLogout = () => {
    setCurrentUser(null)
  }

  const handleAddMember = async () => {
    if (!selectedDbId || !addMemberUsername.trim()) return
    try {
      const member = await sharingApi.addMember(selectedDbId, {
        username: addMemberUsername.trim(),
        role: addMemberRole,
      })
      setMembers(prev => {
        const idx = prev.findIndex(m => m.user_id === member.user_id)
        if (idx >= 0) { const copy = [...prev]; copy[idx] = member; return copy }
        return [...prev, member]
      })
      // 刷新用户列表（可能自动创建了新用户）
      loadUsers()
      setAddMemberUsername('')
      setAddMemberRole('viewer')
      setShowAddMember(false)
    } catch (error: unknown) {
      alert(getErrorMessage(error, '添加协作者失败'))
    }
  }

  const handleUpdateRole = async (userId: number, role: 'editor' | 'viewer') => {
    if (!selectedDbId) return
    try {
      await sharingApi.updateMember(selectedDbId, userId, role)
      setMembers(prev => prev.map(m => m.user_id === userId ? { ...m, role } : m))
    } catch (error: unknown) {
      alert(getErrorMessage(error, '更新角色失败'))
    }
  }

  const handleRemoveMember = async (userId: number) => {
    if (!selectedDbId) return
    if (!confirm('确定移除此协作者？')) return
    try {
      await sharingApi.removeMember(selectedDbId, userId)
      setMembers(prev => prev.filter(m => m.user_id !== userId))
    } catch (error: unknown) {
      alert(getErrorMessage(error, '移除失败'))
    }
  }

  const handleSetOwner = async (userId: number) => {
    if (!selectedDbId) return
    if (!confirm('确定转移所有权？此操作不可逆。')) return
    try {
      await databaseApi.setOwner(selectedDbId, userId)
      loadMembers()
    } catch (error: unknown) {
      alert(getErrorMessage(error, '转移所有权失败'))
    }
  }

  return (
    <div className="page-container sharing-page">
      <div className="page-header">
        <h2 className="page-title">权限管理与协作</h2>
        <p className="page-subtitle">管理成员身份、部门归属与专利库访问权限</p>
      </div>

      {/* 当前用户 */}
      <div style={{
        background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8,
        padding: 16, marginBottom: 20,
      }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, color: '#6b7280', marginBottom: 12 }}>当前身份</h3>
        {currentUser ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 36, height: 36, borderRadius: '50%', background: '#3b82f6',
              color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 14, fontWeight: 600,
            }}>
              {(currentUser.display_name || currentUser.username).charAt(0).toUpperCase()}
            </div>
            <div>
              <div style={{ fontWeight: 600 }}>{currentUser.display_name || currentUser.username}</div>
              <div style={{ fontSize: 12, color: '#9ca3af' }}>@{currentUser.username} · {currentUser.role}</div>
            </div>
            <button
              style={{
                marginLeft: 'auto', fontSize: 12, padding: '4px 12px',
                background: '#f3f4f6', border: '1px solid #d1d5db', borderRadius: 4, cursor: 'pointer',
              }}
              onClick={handleLogout}
            >
              切换身份
            </button>
          </div>
        ) : (
          <div>
            <p style={{ fontSize: 13, color: '#9ca3af', marginBottom: 8 }}>请选择或创建一个身份以使用协作功能</p>
            {users.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
                {users.map(u => (
                  <button
                    key={u.id}
                    style={{
                      fontSize: 12, padding: '6px 12px', background: '#f0f9ff', border: '1px solid #93c5fd',
                      borderRadius: 6, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6,
                    }}
                    onClick={() => handleSelectUser(u)}
                  >
                    <span style={{
                      width: 22, height: 22, borderRadius: '50%', background: '#3b82f6',
                      color: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 10, fontWeight: 600,
                    }}>
                      {(u.display_name || u.username).charAt(0).toUpperCase()}
                    </span>
                    {u.display_name || u.username}
                  </button>
                ))}
              </div>
            )}
            <button
              style={{ fontSize: 12, padding: '6px 14px', background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer' }}
              onClick={() => setShowCreateUser(true)}
            >
              + 创建新用户
            </button>
          </div>
        )}
      </div>

      {/* 创建用户弹窗 */}
      {showCreateUser && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 1000,
        }}>
          <div style={{
            background: '#fff', borderRadius: 12, padding: 24, width: 360, boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
          }}>
            <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16 }}>创建新用户</h3>
            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 12, color: '#6b7280', display: 'block', marginBottom: 4 }}>用户名 *</label>
              <input
                style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13 }}
                value={newUsername}
                onChange={e => setNewUsername(e.target.value)}
                placeholder="如 zhangsan"
                autoFocus
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 12, color: '#6b7280', display: 'block', marginBottom: 4 }}>工号</label>
              <input style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13 }} value={newEmployeeNo} onChange={e => setNewEmployeeNo(e.target.value)} placeholder="例如：RD-001" />
            </div>
            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 12, color: '#6b7280', display: 'block', marginBottom: 4 }}>显示名称</label>
              <input
                style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13 }}
                value={newDisplayName}
                onChange={e => setNewDisplayName(e.target.value)}
                placeholder="如 张三"
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 12, color: '#6b7280', display: 'block', marginBottom: 4 }}>系统角色</label>
              <select
                style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13, background: '#fff' }}
                value={newUserRole}
                onChange={e => setNewUserRole(e.target.value as 'admin' | 'member')}
              >
                <option value="member">成员（member）</option>
                <option value="admin">管理员（admin）</option>
              </select>
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 12, color: '#6b7280', display: 'block', marginBottom: 4 }}>所属部门</label>
              <select
                style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13, background: '#fff' }}
                value={newUserDeptId}
                onChange={e => setNewUserDeptId(e.target.value)}
              >
                <option value="">不指定部门</option>
                {departments.map(d => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </select>
            </div>
            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 12, color: '#6b7280', display: 'block', marginBottom: 4 }}>小组</label>
              <select style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13, background: '#fff' }} value={newUserGroupId} onChange={e => setNewUserGroupId(e.target.value)}>
                <option value="">不指定小组</option>
                {departments.filter(d => d.parent_id === Number(newUserDeptId)).map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </div>
            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 12, color: '#6b7280', display: 'block', marginBottom: 4 }}>产品线</label>
              <select style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13, background: '#fff' }} value={newUserProductLineId} onChange={e => setNewUserProductLineId(e.target.value)}>
                <option value="">不指定产品线</option>
                {productLines.map(line => <option key={line.id} value={line.id}>{line.code ? `${line.code} - ` : ''}{line.name}</option>)}
              </select>
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 12, color: '#6b7280', display: 'block', marginBottom: 4 }}>业务身份</label>
              <input style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13 }} value={newUserOrgRole} onChange={e => setNewUserOrgRole(e.target.value)} placeholder="如：研发工程师、检索" />
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button
                style={{ fontSize: 13, padding: '6px 16px', background: '#f3f4f6', border: '1px solid #d1d5db', borderRadius: 6, cursor: 'pointer' }}
                onClick={() => { setShowCreateUser(false); setNewUsername(''); setNewDisplayName('') }}
              >
                取消
              </button>
              <button
                style={{ fontSize: 13, padding: '6px 16px', background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer' }}
                onClick={handleCreateUser}
              >
                创建
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 协作者管理 */}
      <div style={{
        background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8,
        padding: 16, marginBottom: 20,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: '#6b7280' }}>库的协作者</h3>
          <select
            style={{
              fontSize: 13, padding: '6px 10px', border: '1px solid #d1d5db', borderRadius: 6,
              background: '#fff', minWidth: 180,
            }}
            value={selectedDbId ?? ''}
            onChange={e => setSelectedDbId(Number(e.target.value))}
          >
            <option value="">选择库...</option>
            {databases.map(d => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
        </div>

        {!selectedDbId ? (
          <p style={{ fontSize: 13, color: '#9ca3af' }}>请先选择一个库以管理协作者</p>
        ) : (
          <>
            {/* 成员列表 */}
            {members.length === 0 ? (
              <p style={{ fontSize: 13, color: '#9ca3af', marginBottom: 12 }}>
                暂无协作者（库所有者自动拥有全部权限）
              </p>
            ) : (
              <div style={{ marginBottom: 12 }}>
                {members.map(m => (
                  <div
                    key={m.id}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 10,
                      padding: '8px 12px', borderBottom: '1px solid #f3f4f6',
                    }}
                  >
                    <span style={{
                      width: 28, height: 28, borderRadius: '50%', background: m.role === 'owner' ? '#f59e0b' : '#6366f1',
                      color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 11, fontWeight: 600, flexShrink: 0,
                    }}>
                      {(m.display_name || m.username).charAt(0).toUpperCase()}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 500, fontSize: 13 }}>
                        {m.display_name || m.username}
                        {m.role === 'owner' && (
                          <span style={{
                            marginLeft: 6, fontSize: 10, padding: '1px 6px', background: '#fef3c7',
                            color: '#92400e', borderRadius: 4, fontWeight: 600,
                          }}>所有者</span>
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: '#9ca3af' }}>@{m.username}</div>
                    </div>
                    {m.role !== 'owner' && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <select
                          style={{
                            fontSize: 11, padding: '2px 6px', border: '1px solid #d1d5db', borderRadius: 4,
                            background: '#fff',
                          }}
                          value={m.role}
                          onChange={e => handleUpdateRole(m.user_id, e.target.value as 'editor' | 'viewer')}
                        >
                          <option value="editor">编辑者</option>
                          <option value="viewer">查看者</option>
                        </select>
                        <button
                          style={{ fontSize: 11, padding: '2px 8px', background: '#fee2e2', color: '#991b1b', border: 'none', borderRadius: 4, cursor: 'pointer' }}
                          onClick={() => handleRemoveMember(m.user_id)}
                        >
                          移除
                        </button>
                        <button
                          style={{ fontSize: 11, padding: '2px 8px', background: '#fef3c7', color: '#92400e', border: 'none', borderRadius: 4, cursor: 'pointer' }}
                          onClick={() => handleSetOwner(m.user_id)}
                          title="转移所有权"
                        >
                          设为所有者
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* 添加协作者 */}
            {showAddMember ? (
              <div style={{
                padding: 12, background: '#f9fafb', borderRadius: 6, border: '1px solid #e5e7eb',
              }}>
                <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 8 }}>添加协作者</div>
                <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                  <input
                    style={{ flex: 1, padding: '6px 10px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 13 }}
                    placeholder="输入用户名"
                    value={addMemberUsername}
                    onChange={e => setAddMemberUsername(e.target.value)}
                    autoFocus
                  />
                  <select
                    style={{ padding: '6px 8px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 13, background: '#fff' }}
                    value={addMemberRole}
                    onChange={e => setAddMemberRole(e.target.value as 'editor' | 'viewer')}
                  >
                    <option value="viewer">查看者</option>
                    <option value="editor">编辑者</option>
                  </select>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    style={{ fontSize: 12, padding: '4px 12px', background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}
                    onClick={handleAddMember}
                  >
                    添加
                  </button>
                  <button
                    style={{ fontSize: 12, padding: '4px 12px', background: '#f3f4f6', border: '1px solid #d1d5db', borderRadius: 4, cursor: 'pointer' }}
                    onClick={() => { setShowAddMember(false); setAddMemberUsername('') }}
                  >
                    取消
                  </button>
                </div>
                <p style={{ fontSize: 11, color: '#9ca3af', marginTop: 6 }}>
                  若用户名不存在，将自动创建对应用户
                </p>
              </div>
            ) : (
              <button
                style={{ fontSize: 12, padding: '6px 14px', background: '#f0f9ff', border: '1px solid #93c5fd', borderRadius: 6, cursor: 'pointer', color: '#1d4ed8' }}
                onClick={() => setShowAddMember(true)}
              >
                + 添加协作者
              </button>
            )}
          </>
        )}
      </div>

      {/* 所有用户列表 */}
      <div style={{
        background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8,
        padding: 16,
      }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, color: '#6b7280', marginBottom: 12 }}>所有用户</h3>
        {users.length === 0 ? (
          <p style={{ fontSize: 13, color: '#9ca3af' }}>暂无用户，请先创建</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
                <th style={{ textAlign: 'left', padding: '8px 4px', fontWeight: 500, color: '#6b7280' }}>用户</th>
                <th style={{ textAlign: 'left', padding: '8px 4px', fontWeight: 500, color: '#6b7280' }}>用户名</th>
                <th style={{ textAlign: 'left', padding: '8px 4px', fontWeight: 500, color: '#6b7280' }}>工号</th>
                <th style={{ textAlign: 'left', padding: '8px 4px', fontWeight: 500, color: '#6b7280' }}>系统角色</th>
                <th style={{ textAlign: 'left', padding: '8px 4px', fontWeight: 500, color: '#6b7280' }}>部门</th>
                <th style={{ textAlign: 'left', padding: '8px 4px', fontWeight: 500, color: '#6b7280' }}>小组 / 业务身份</th>
                <th style={{ textAlign: 'left', padding: '8px 4px', fontWeight: 500, color: '#6b7280' }}>产品线</th>
                <th style={{ textAlign: 'left', padding: '8px 4px', fontWeight: 500, color: '#6b7280' }}>状态</th>
                <th style={{ textAlign: 'right', padding: '8px 4px', fontWeight: 500, color: '#6b7280' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => {
                const isEditing = editingUserId === u.id
                return (
                  <tr key={u.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                    <td style={{ padding: '8px 4px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{
                          width: 24, height: 24, borderRadius: '50%', background: '#6366f1',
                          color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: 10, fontWeight: 600,
                        }}>
                          {(u.display_name || u.username).charAt(0).toUpperCase()}
                        </span>
                        {u.display_name || u.username}
                      </div>
                    </td>
                    <td style={{ padding: '8px 4px', color: '#9ca3af' }}>@{u.username}</td>
                    <td style={{ padding: '8px 4px', color: '#64748b' }}>
                      {isEditing ? <input style={{ width: 90, fontSize: 11, padding: '3px 5px' }} value={editEmployeeNo} onChange={e => setEditEmployeeNo(e.target.value)} /> : (u.employee_no || '-')}
                    </td>
                    <td style={{ padding: '8px 4px' }}>
                      {isEditing ? (
                        <select
                          style={{ fontSize: 11, padding: '2px 6px', border: '1px solid #d1d5db', borderRadius: 4, background: '#fff' }}
                          value={u.role === 'admin' ? 'admin' : 'member'}
                          onChange={e => handleUpdateUserRole(u.id, e.target.value as 'admin' | 'member')}
                        >
                          <option value="member">成员</option>
                          <option value="admin">管理员</option>
                        </select>
                      ) : (
                        <span style={{
                          fontSize: 11, padding: '1px 6px', borderRadius: 4,
                          background: u.role === 'admin' ? '#ede9fe' : '#f3f4f6',
                          color: u.role === 'admin' ? '#6d28d9' : '#6b7280',
                        }}>
                          {u.role === 'admin' ? '管理员' : '成员'}
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '8px 4px', color: '#64748b' }}>
                      {isEditing ? (
                        <div style={{ display: 'grid', gap: 4 }}>
                          <select style={{ fontSize: 11, padding: '2px 6px' }} value={editGroupId} onChange={e => setEditGroupId(e.target.value)}>
                            <option value="">无小组</option>
                            {departments.filter(d => d.parent_id === Number(editDeptId)).map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                          </select>
                          <input style={{ fontSize: 11, padding: '3px 5px' }} value={editOrgRole} onChange={e => setEditOrgRole(e.target.value)} placeholder="业务身份" />
                        </div>
                      ) : <>{u.group_name || '-'}{u.organization_role ? ` / ${u.organization_role}` : ''}</>}
                    </td>
                    <td style={{ padding: '8px 4px', color: '#64748b' }}>
                      {isEditing ? <select style={{ fontSize: 11, padding: '2px 6px' }} value={editProductLineId} onChange={e => setEditProductLineId(e.target.value)}><option value="">无产品线</option>{productLines.map(line => <option key={line.id} value={line.id}>{line.code || line.name}</option>)}</select> : (u.product_line_name || '-')}
                    </td>
                    <td style={{ padding: '8px 4px' }}>
                      {isEditing ? (
                        <select
                          style={{ fontSize: 11, padding: '2px 6px', border: '1px solid #d1d5db', borderRadius: 4, background: '#fff', maxWidth: 120 }}
                          value={editDeptId}
                          onChange={e => setEditDeptId(e.target.value)}
                        >
                          <option value="">无部门</option>
                          {departments.map(d => (
                            <option key={d.id} value={d.id}>{d.name}</option>
                          ))}
                        </select>
                      ) : (
                        <span style={{ fontSize: 11, color: u.department_name ? '#374151' : '#9ca3af' }}>
                          {u.department_name || '—'}
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '8px 4px' }}>
                      <span style={{
                        fontSize: 11, padding: '1px 6px', borderRadius: 4,
                        background: u.is_active ? '#dcfce7' : '#fee2e2',
                        color: u.is_active ? '#166534' : '#991b1b',
                      }}>
                        {u.is_active ? '活跃' : '禁用'}
                      </span>
                    </td>
                    <td style={{ padding: '8px 4px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                      {isEditing ? (
                        <>
                          <button
                            style={{ fontSize: 11, padding: '2px 8px', background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', marginRight: 4 }}
                            onClick={() => handleUpdateUser(u.id)}
                          >
                            保存
                          </button>
                          <button
                            style={{ fontSize: 11, padding: '2px 8px', background: '#f3f4f6', color: '#6b7280', border: 'none', borderRadius: 4, cursor: 'pointer' }}
                            onClick={() => setEditingUserId(null)}
                          >
                            取消
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            style={{ fontSize: 11, padding: '2px 8px', background: '#f3f4f6', color: '#6b7280', border: 'none', borderRadius: 4, cursor: 'pointer', marginRight: 4 }}
                            onClick={() => {
                              setEditingUserId(u.id)
                              setEditEmployeeNo(u.employee_no || '')
                              setEditDeptId(u.department_id ? String(u.department_id) : '')
                              setEditGroupId(u.group_id ? String(u.group_id) : '')
                              setEditProductLineId(u.product_line_id ? String(u.product_line_id) : '')
                              setEditOrgRole(u.organization_role || '')
                            }}
                          >
                            编辑
                          </button>
                          <button
                            style={{
                              fontSize: 11, padding: '2px 8px', background: currentUser?.id === u.id ? '#3b82f6' : '#f3f4f6',
                              color: currentUser?.id === u.id ? '#fff' : '#6b7280',
                              border: 'none', borderRadius: 4, cursor: 'pointer',
                            }}
                            onClick={() => handleSelectUser(u)}
                          >
                            {currentUser?.id === u.id ? '当前' : '切换'}
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
