import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuth } from '@/context/auth'
import { useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { toast } from 'sonner'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username || !password) {
      toast.error('请输入用户名和密码')
      return
    }
    setLoading(true)
    try {
      await login(username, password)
      navigate('/')
    } catch (err: any) {
      toast.error(err?.response?.data?.message || err?.response?.data?.detail || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative min-h-screen w-full overflow-hidden">
      {/* Video background — desktop only */}
      <video
        autoPlay
        muted
        loop
        playsInline
        preload="metadata"
        className="hidden md:block absolute inset-0 w-full h-full object-cover z-0"
      >
        <source src="/backvideos.mp4" type="video/mp4" />
      </video>

      {/* Static gradient background — mobile fallback */}
      <div
        className="block md:hidden absolute inset-0 z-0"
        style={{
          background: 'linear-gradient(135deg, #f7f3eb 0%, #e0d8cc 50%, #c4b8a8 100%)',
        }}
      />

      {/* Top white-to-transparent gradient overlay for readability */}
      <div
        className="absolute inset-x-0 top-0 h-[60vh] pointer-events-none z-[1]"
        style={{
          background: 'linear-gradient(180deg, rgba(247,243,235,0.95) 0%, rgba(247,243,235,0) 100%)',
        }}
      />

      {/* Content */}
      <div className="relative z-[2] min-h-screen flex flex-col">
        {/* Navigation bar */}
        <nav className="flex items-center justify-between px-8 md:px-16 py-6">
          <span className="text-2xl font-bold text-primary">CNKI</span>
          <Button variant="ghost" className="text-primary text-sm">
            帮助中心
          </Button>
        </nav>

        {/* Login card */}
        <div className="flex-1 flex items-center justify-center px-4 pb-16">
          <Card className="w-full max-w-md bg-white/60 backdrop-blur-xl border-white/30 shadow-2xl">
            <CardHeader className="text-center">
              <CardTitle className="text-xl text-foreground">
                CNKI定题检索服务
              </CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="username">用户名</Label>
                  <Input
                    id="username"
                    autoComplete="username"
                    placeholder="请输入用户名"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="password">密码</Label>
                  <Input
                    id="password"
                    type="password"
                    autoComplete="current-password"
                    placeholder="请输入密码"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </div>
                <Button type="submit" className="w-full" disabled={loading}>
                  {loading ? '登录中...' : '登录'}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
