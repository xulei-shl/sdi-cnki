import { Button } from '@/components/ui/button'
import { useNavigate } from 'react-router-dom'

export default function NotFoundPage() {
  const navigate = useNavigate()
  return (
    <div className="h-full flex flex-col items-center justify-center">
      <h1 className="text-6xl font-bold text-muted-foreground">404</h1>
      <p className="mt-2 text-muted-foreground">页面不存在</p>
      <Button className="mt-4" onClick={() => navigate('/')}>返回首页</Button>
    </div>
  )
}
