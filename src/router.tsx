import { lazy, Suspense, type ReactNode } from 'react'
import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppLayout } from '@/components/layout/app-layout'
import { Skeleton } from '@/components/ui/skeleton'

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

function PageSkeleton() {
  return (
    <div className="p-8 space-y-6">
      <Skeleton className="h-8 w-[320px]" />
      <div className="space-y-3">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full rounded-md" />
        ))}
      </div>
    </div>
  )
}

function SuspenseWrapper({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<PageSkeleton />}>
      {children}
    </Suspense>
  )
}

/* P0-1: Preload all route chunks during idle time so tab switching is instant */
const pagePreloaders = [
  () => import('@/pages/meta-task'),
  () => import('@/pages/task-instance'),
  () => import('@/pages/task-result'),
  () => import('@/pages/prompt'),
  () => import('@/pages/user/settings'),
  () => import('@/pages/usage-guide'),
  () => import('@/pages/system/user'),
  () => import('@/pages/system/llm-config'),
  () => import('@/pages/system/prompt-template'),
  () => import('@/pages/system/config'),
  () => import('@/pages/system/notification-configs'),
]

if ('requestIdleCallback' in window) {
  requestIdleCallback(() => {
    pagePreloaders.forEach(preload => preload())
  }, { timeout: 3000 })
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
