import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuth } from '@/context/auth'
import { useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { toast } from 'sonner'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import helpContent from './help-content.md?raw'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)
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
          <img src="/logo.svg" alt="SDI-CNKI" className="h-7 w-auto" />
          <Button variant="ghost" className="text-primary text-sm" onClick={() => setHelpOpen(true)}>
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

      {/* Help center dialog */}
      <Dialog open={helpOpen} onOpenChange={setHelpOpen}>
        <DialogContent className="max-w-2xl max-h-[80vh] p-0">
          <DialogTitle className="sr-only">帮助中心</DialogTitle>
          <ScrollArea className="h-[80vh]">
            <div className="px-8 py-6 prose prose-stone prose-headings:font-semibold prose-headings:text-foreground prose-h1:text-xl prose-h1:mb-4 prose-h2:text-base prose-h2:mt-6 prose-h2:mb-3 prose-h2:text-muted-foreground prose-p:text-sm prose-p:leading-relaxed prose-li:text-sm prose-li:marker:text-muted-foreground/50 prose-strong:text-foreground prose-a:text-primary prose-a:no-underline hover:prose-a:underline">
              <Markdown remarkPlugins={[remarkGfm]}>
                {helpContent}
              </Markdown>
            </div>
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </div>
  )
}
