import { RouterProvider } from 'react-router-dom'
import { router } from '@/router'
import { AuthProvider } from '@/context/auth'
import { Toaster } from '@/components/ui/sonner'

export default function App() {
  return (
    <AuthProvider>
      <RouterProvider router={router} />
      <Toaster />
    </AuthProvider>
  )
}
