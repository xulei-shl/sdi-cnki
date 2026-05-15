import { useAuth } from '@/context/auth'
import { cn } from '@/lib/utils'
import { NavLink } from 'react-router-dom'

const navItems = [
  { to: '/meta-tasks', label: '任务模板', icon: '📋', roles: ['admin', 'user'] },
  { to: '/task-instances', label: '任务实例', icon: '📊', roles: ['admin', 'user'] },
]

const adminItems = [
  { to: '/system/users', label: '用户管理', icon: '👤' },
  { to: '/system/llm-configs', label: '大模型管理', icon: '🤖' },
  { to: '/system/prompts', label: '提示词管理', icon: '📝' },
  { to: '/system/config', label: '系统配置', icon: '⚙️' },
]

export function Sidebar() {
  const { user } = useAuth()

  return (
    <aside className="w-60 border-r bg-background flex flex-col shrink-0">
      <div className="h-14 flex items-center px-4 border-b">
        <h1 className="font-semibold text-base">CNKI 定题服务</h1>
      </div>

      <nav className="flex-1 p-2 space-y-1 overflow-y-auto">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors',
                isActive
                  ? 'bg-primary/10 text-primary font-medium'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
              )
            }
          >
            <span>{item.icon}</span>
            <span>{item.label}</span>
          </NavLink>
        ))}

        {user?.role === 'admin' && (
          <>
            <div className="pt-4 pb-1 px-3 text-xs font-medium text-muted-foreground uppercase">
              设置
            </div>
            {adminItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors',
                    isActive
                      ? 'bg-primary/10 text-primary font-medium'
                      : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                  )
                }
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </NavLink>
            ))}
          </>
        )}
      </nav>
    </aside>
  )
}
