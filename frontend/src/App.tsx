import { RouterProvider } from 'react-router-dom'

import { AuthProvider } from './modules/auth/AuthProvider'
import { router } from './routes/router'

export default function App() {
  return (
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  )
}
