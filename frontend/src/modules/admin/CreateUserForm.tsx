import { useState, type FormEvent } from 'react'

import { ApiError } from '../../services/apiClient'
import { adminService } from '../../services/adminService'
import type { User } from '../../types/user'
import { errorMessage } from './format'

const MIN_PASSWORD_LENGTH = 8

export default function CreateUserForm({ onCreated }: { onCreated: (user: User) => void }) {
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      onCreated(await adminService.createUser({ full_name: fullName, email, password }))
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError('Ya existe una cuenta con ese correo.')
      } else if (err instanceof ApiError && err.status === 422) {
        setError('Revisa los datos ingresados.')
      } else {
        setError(errorMessage(err))
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="panel-form" onSubmit={handleSubmit}>
      <h2>Nueva cuenta de usuario</h2>
      <div className="toolbar">
        <label>
          Nombre completo
          <input
            type="text"
            required
            maxLength={120}
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
          />
        </label>
        <label>
          Correo electrónico
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Contraseña inicial
          <input
            type="password"
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <button type="submit" disabled={submitting}>
          {submitting ? 'Creando…' : 'Crear cuenta'}
        </button>
      </div>
      <p className="form-hint">
        La cuenta se crea con rol Usuario y queda habilitada. La contraseña debe tener al menos{' '}
        {MIN_PASSWORD_LENGTH} caracteres.
      </p>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </form>
  )
}
