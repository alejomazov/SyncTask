import { createBrowserRouter, Navigate } from 'react-router-dom'

import AdminPage from '../modules/admin/AdminPage'
import ChatPage from '../modules/chat/ChatPage'
import DashboardPage from '../modules/dashboard/DashboardPage'

export const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/dashboard" replace /> },
  { path: '/chat', element: <ChatPage /> },
  { path: '/dashboard', element: <DashboardPage /> },
  { path: '/admin', element: <AdminPage /> },
])
