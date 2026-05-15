import { useAuth } from '@/context/auth'
import { Button } from '@/components/ui/button'
import { useNavigate } from 'react-router-dom'

export function Header() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <header className="h-14 border-b bg-background flex items-center justify-between px-4 shrink-0">
      <div />
      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground">
          {user?.username}
          <span className="ml-1 text-xs">
            ({user?.role === 'admin' ? '管理员' : '普通用户'})
          </span>
        </span>
        <Button variant="outline" size="sm" onClick={handleLogout}>
          退出
        </Button>
      </div>
    </header>
  )
}
