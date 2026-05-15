import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { toast } from 'sonner'
import { getUsers, createUser, updateUser, deleteUser } from '@/api/users'
import type { User, UserRole } from '@/types'

export default function UserManagePage() {
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editUser, setEditUser] = useState<User | null>(null)
  const [saving, setSaving] = useState(false)

  // Form state
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<UserRole>('user')
  const [isActive, setIsActive] = useState(true)

  const fetchUsers = async () => {
    setLoading(true)
    try {
      const res = await getUsers()
      setUsers(res.data.items || [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchUsers() }, [])

  const openCreate = () => {
    setEditUser(null)
    setUsername('')
    setPassword('')
    setEmail('')
    setRole('user')
    setIsActive(true)
    setDialogOpen(true)
  }

  const openEdit = (user: User) => {
    setEditUser(user)
    setUsername(user.username)
    setPassword('')
    setEmail(user.email || '')
    setRole(user.role)
    setIsActive(user.is_active)
    setDialogOpen(true)
  }

  const handleSave = async () => {
    if (!username.trim()) { toast.error('请输入用户名'); return }
    if (!editUser && !password) { toast.error('请输入密码'); return }
    setSaving(true)
    try {
      const data: any = { username: username.trim(), email: email || null, role, is_active: isActive }
      if (password) data.password = password
      if (editUser) {
        await updateUser(editUser.id, data)
        toast.success('更新成功')
      } else {
        await createUser(data)
        toast.success('创建成功')
      }
      setDialogOpen(false)
      fetchUsers()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || '操作失败')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('确认删除此用户？')) return
    try {
      await deleteUser(id)
      toast.success('删除成功')
      fetchUsers()
    } catch {
      toast.error('删除失败')
    }
  }

  const formatDate = (d: string) => d?.slice(0, 16).replace('T', ' ') || '-'

  return (
    <div className="p-6 h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">用户管理</h2>
        <Button onClick={openCreate}>新建用户</Button>
      </div>

      <div className="flex-1 overflow-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>用户名</TableHead>
              <TableHead>邮箱</TableHead>
              <TableHead>角色</TableHead>
              <TableHead>状态</TableHead>
              <TableHead>创建时间</TableHead>
              <TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">加载中...</TableCell></TableRow>
            ) : users.length === 0 ? (
              <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">暂无用户</TableCell></TableRow>
            ) : users.map((user) => (
              <TableRow key={user.id}>
                <TableCell className="font-medium">{user.username}</TableCell>
                <TableCell className="text-muted-foreground">{user.email || '-'}</TableCell>
                <TableCell>
                  <Badge variant={user.role === 'admin' ? 'default' : 'secondary'}>
                    {user.role === 'admin' ? '管理员' : '普通用户'}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Badge variant={user.is_active ? 'success' : 'secondary'}>
                    {user.is_active ? '启用' : '禁用'}
                  </Badge>
                </TableCell>
                <TableCell>{formatDate(user.created_at)}</TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
                    <Button variant="ghost" size="sm" onClick={() => openEdit(user)}>编辑</Button>
                    <Button variant="ghost" size="sm" className="text-destructive" onClick={() => handleDelete(user.id)}>删除</Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{editUser ? '编辑用户' : '新建用户'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1">
              <Label>用户名 <span className="text-destructive">*</span></Label>
              <Input value={username} onChange={(e) => setUsername(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>密码 {!editUser && <span className="text-destructive">*</span>}</Label>
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder={editUser ? '留空不修改' : ''} />
            </div>
            <div className="space-y-1">
              <Label>邮箱</Label>
              <Input value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>角色</Label>
              <Select value={role} onChange={(e) => setRole(e.target.value as UserRole)}>
                <option value="user">普通用户</option>
                <option value="admin">管理员</option>
              </Select>
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
              <Label>启用</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>取消</Button>
            <Button onClick={handleSave} disabled={saving}>{saving ? '保存中...' : '保存'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
