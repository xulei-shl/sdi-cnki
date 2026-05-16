import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppLayout } from '@/components/layout/app-layout'
import LoginPage from '@/pages/login'
import MetaTaskPage from '@/pages/meta-task'
import TaskInstancePage from '@/pages/task-instance'
import TaskResultPage from '@/pages/task-result'
import UserManagePage from '@/pages/system/user'
import LlmConfigPage from '@/pages/system/llm-config'
import PromptPage from '@/pages/prompt'
import PromptTemplatePage from '@/pages/system/prompt-template'
import SystemConfigPage from '@/pages/system/config'
import NotFoundPage from '@/pages/error/404'
import ForbiddenPage from '@/pages/error/403'

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/meta-tasks" replace /> },
      { path: 'meta-tasks', element: <MetaTaskPage /> },
      { path: 'task-instances', element: <TaskInstancePage /> },
      { path: 'task-instances/:id/results', element: <TaskResultPage /> },
      { path: 'prompts', element: <PromptPage /> },
      { path: 'system/users', element: <UserManagePage /> },
      { path: 'system/llm-configs', element: <LlmConfigPage /> },
      { path: 'system/prompts', element: <PromptPage /> },
      { path: 'system/prompt-templates', element: <PromptTemplatePage /> },
      { path: 'system/config', element: <SystemConfigPage /> },
      { path: '403', element: <ForbiddenPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
