import { createBrowserRouter, Navigate } from 'react-router-dom'

import AppLayout from '../layouts/AppLayout'
import AdminPage from '../modules/admin/AdminPage'
import LoginPage from '../modules/auth/LoginPage'
import RegisterPage from '../modules/auth/RegisterPage'
import ChatPage from '../modules/chat/ChatPage'
import ConnectionsPage from '../modules/connections/ConnectionsPage'
import AgendaPage from '../modules/dashboard/AgendaPage'
import InboxPage from '../modules/dashboard/InboxPage'
import TasksPage from '../modules/dashboard/TasksPage'
import AccountSettingsPage from '../modules/settings/AccountSettingsPage'
import AiSettingsPage from '../modules/settings/AiSettingsPage'
import SettingsPage from '../modules/settings/SettingsPage'
import TodayPage from '../modules/today/TodayPage'
import ProtectedRoute from './ProtectedRoute'

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  { path: '/register', element: <RegisterPage /> },
  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { path: '/', element: <Navigate to="/dashboard" replace /> },
          { path: '/dashboard', element: <TodayPage /> },
          { path: '/agenda', element: <AgendaPage /> },
          { path: '/inbox', element: <InboxPage /> },
          { path: '/tasks', element: <TasksPage /> },
          { path: '/chat', element: <ChatPage /> },
          { path: '/connections', element: <ConnectionsPage /> },
          {
            path: '/settings',
            element: <SettingsPage />,
            children: [
              { index: true, element: <Navigate to="/settings/ai" replace /> },
              { path: 'ai', element: <AiSettingsPage /> },
              { path: 'account', element: <AccountSettingsPage /> },
            ],
          },
          {
            element: <ProtectedRoute role="admin" />,
            children: [{ path: '/admin', element: <AdminPage /> }],
          },
        ],
      },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])
