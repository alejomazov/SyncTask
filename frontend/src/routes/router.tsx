import { createBrowserRouter, Navigate } from 'react-router-dom'

import AppLayout from '../layouts/AppLayout'
import AdminPage from '../modules/admin/AdminPage'
import LoginPage from '../modules/auth/LoginPage'
import RegisterPage from '../modules/auth/RegisterPage'
import ChatPage from '../modules/chat/ChatPage'
import ConnectionsPage from '../modules/connections/ConnectionsPage'
import DashboardPage from '../modules/dashboard/DashboardPage'
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
          { path: '/dashboard', element: <DashboardPage /> },
          { path: '/chat', element: <ChatPage /> },
          { path: '/connections', element: <ConnectionsPage /> },
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
