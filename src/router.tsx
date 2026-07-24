import { lazy, Suspense, type ReactNode } from 'react'
import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppLayout } from '@/components/layout/app-layout'
import { Loader2 } from 'lucide-react'

const LoginPage = lazy(() => import('@/pages/login'))
const MetaTaskPage = lazy(() => import('@/pages/meta-task'))
const TaskInstancePage = lazy(() => import('@/pages/task-instance'))
const TaskResultPage = lazy(() => import('@/pages/task-result'))
const UserManagePage = lazy(() => import('@/pages/system/user'))
const LlmConfigPage = lazy(() => import('@/pages/system/llm-config'))
const PromptPage = lazy(() => import('@/pages/prompt'))
const PromptTemplatePage = lazy(() => import('@/pages/system/prompt-template'))
const SystemConfigPage = lazy(() => import('@/pages/system/config'))
const AdminNotificationConfigsPage = lazy(() => import('@/pages/system/notification-configs'))
const UserSettingsPage = lazy(() => import('@/pages/user/settings'))
const UsageGuidePage = lazy(() => import('@/pages/usage-guide'))
const NotFoundPage = lazy(() => import('@/pages/error/404'))
const ForbiddenPage = lazy(() => import('@/pages/error/403'))

function SuspenseWrapper({ children }: { children: ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      }
    >
      {children}
    </Suspense>
  )
}

export const router = createBrowserRouter([
  {
    path: '/login',
    element: (
      <Suspense fallback={null}>
        <LoginPage />
      </Suspense>
    ),
  },
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/meta-tasks" replace /> },
      { path: 'meta-tasks', element: <SuspenseWrapper><MetaTaskPage /></SuspenseWrapper> },
      { path: 'task-instances', element: <SuspenseWrapper><TaskInstancePage /></SuspenseWrapper> },
      { path: 'task-instances/:id/results', element: <SuspenseWrapper><TaskResultPage /></SuspenseWrapper> },
      { path: 'prompts', element: <SuspenseWrapper><PromptPage /></SuspenseWrapper> },
      { path: 'settings', element: <SuspenseWrapper><UserSettingsPage /></SuspenseWrapper> },
      { path: 'system/users', element: <SuspenseWrapper><UserManagePage /></SuspenseWrapper> },
      { path: 'system/llm-configs', element: <SuspenseWrapper><LlmConfigPage /></SuspenseWrapper> },
      { path: 'system/prompt-templates', element: <SuspenseWrapper><PromptTemplatePage /></SuspenseWrapper> },
      { path: 'system/config', element: <SuspenseWrapper><SystemConfigPage /></SuspenseWrapper> },
      { path: 'system/notification-configs', element: <SuspenseWrapper><AdminNotificationConfigsPage /></SuspenseWrapper> },
      { path: 'usage-guide', element: <SuspenseWrapper><UsageGuidePage /></SuspenseWrapper> },
      { path: '403', element: <SuspenseWrapper><ForbiddenPage /></SuspenseWrapper> },
      { path: '*', element: <SuspenseWrapper><NotFoundPage /></SuspenseWrapper> },
    ],
  },
])
