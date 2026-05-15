import { Outlet } from 'react-router-dom'
import { Sidebar } from './sidebar'
import { Header } from './header'

export function AppLayout() {
  return (
    <div className="h-screen flex overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header />
        <main className="flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
