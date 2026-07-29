/**
 * 应用路由表（frontend-design.md §8：页面/路由）。
 *
 * AppLayout 为壳，子路由渲染各页面：
 * - `/` → 重定向 `/dashboard`（概览）；
 * - `/tasks`、`/tasks/new`、`/tasks/:roomId`（列表/添加/详情）；
 * - `/settings`、`/settings/tasks/:roomId`（全局/任务级设置，M31）；
 * - `/login`、`/about`（扫码登录/关于，M32）；
 * - `*` → 兜底重定向 `/dashboard`。
 *
 * 导出 `routes` 供测试用 createMemoryRouter 装配；`createAppRouter`
 * 供入口 main.tsx 用 createBrowserRouter。
 */
import { createBrowserRouter, Navigate, type RouteObject } from 'react-router'

import { AppLayout } from '../layouts/AppLayout'
import { AboutPage } from '../pages/AboutPage'
import { DashboardPage } from '../pages/DashboardPage'
import { LoginPage } from '../pages/LoginPage'
import { SettingsPage } from '../pages/SettingsPage'
import { TaskSettingsPage } from '../pages/TaskSettingsPage'
import { NewTaskPage } from '../pages/tasks/NewTaskPage'
import { TaskDetailPage } from '../pages/tasks/TaskDetailPage'
import { TaskListPage } from '../pages/tasks/TaskListPage'

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: 'dashboard', element: <DashboardPage /> },
      { path: 'tasks', element: <TaskListPage /> },
      { path: 'tasks/new', element: <NewTaskPage /> },
      { path: 'tasks/:roomId', element: <TaskDetailPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: 'settings/tasks/:roomId', element: <TaskSettingsPage /> },
      { path: 'login', element: <LoginPage /> },
      { path: 'about', element: <AboutPage /> },
      { path: '*', element: <Navigate to="/dashboard" replace /> },
    ],
  },
]

/** 应用级 BrowserRouter（消费 Vite `<base href>`，M34 子路径部署）。 */
export function createAppRouter() {
  return createBrowserRouter(routes, {
    basename: import.meta.env.BASE_URL.replace(/\/$/, '') || undefined,
  })
}
