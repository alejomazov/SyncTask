import { useCallback, useEffect, useState, type FormEvent } from 'react'

import Pagination from '../../components/Pagination'
import { ApiError } from '../../services/apiClient'
import { adminService } from '../../services/adminService'
import type { Page } from '../../types/admin'
import type { User } from '../../types/user'
import { useAuth } from '../auth/useAuth'
import CreateUserForm from './CreateUserForm'
import { errorMessage, formatDateTime } from './format'

const PAGE_SIZE = 10

export default function UsersTab() {
  const { user: currentUser } = useAuth()
  const [data, setData] = useState<Page<User> | null>(null)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [error, setError] = useState<string | null>(null)
  const [updatingId, setUpdatingId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setData(await adminService.listUsers({ search, page, page_size: PAGE_SIZE }))
      setError(null)
    } catch (err) {
      setError(errorMessage(err))
    }
  }, [search, page])

  useEffect(() => {
    void load()
  }, [load])

  async function handleCreated(created: User) {
    setCreating(false)
    setNotice(`Cuenta creada para ${created.email}.`)
    await load()
  }

  function handleSearch(event: FormEvent) {
    event.preventDefault()
    setPage(1)
    setSearch(searchInput)
  }

  async function toggleActive(target: User) {
    const verb = target.is_active ? 'deshabilitar' : 'habilitar'
    if (!window.confirm(`¿Seguro que quieres ${verb} la cuenta de ${target.email}?`)) return

    setUpdatingId(target.id)
    try {
      await adminService.setUserActive(target.id, !target.is_active)
      await load()
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? 'No puedes deshabilitar tu propia cuenta.'
          : errorMessage(err),
      )
    } finally {
      setUpdatingId(null)
    }
  }

  return (
    <section>
      <form className="toolbar" onSubmit={handleSearch}>
        <input
          type="search"
          placeholder="Buscar por nombre o correo"
          aria-label="Buscar por nombre o correo"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
        <button type="submit">Buscar</button>
        <button
          type="button"
          className="button-secondary toolbar-end"
          onClick={() => {
            setNotice(null)
            setCreating(!creating)
          }}
        >
          {creating ? 'Cancelar' : 'Nueva cuenta'}
        </button>
      </form>

      {creating && <CreateUserForm onCreated={(created) => void handleCreated(created)} />}

      {notice && (
        <p className="form-success" role="status">
          {notice}
        </p>
      )}

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {data === null ? (
        !error && <p className="page-loading">Cargando…</p>
      ) : (
        <>
          <table className="data-table">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Correo</th>
                <th>Rol</th>
                <th>Estado</th>
                <th>Creada</th>
                <th aria-label="Acciones" />
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => (
                <tr key={item.id}>
                  <td>{item.full_name}</td>
                  <td>{item.email}</td>
                  <td>{item.role === 'admin' ? 'Administrador' : 'Usuario'}</td>
                  <td>
                    <span className={item.is_active ? 'badge badge-ok' : 'badge badge-off'}>
                      {item.is_active ? 'Habilitada' : 'Deshabilitada'}
                    </span>
                  </td>
                  <td>{formatDateTime(item.created_at)}</td>
                  <td className="cell-actions">
                    {item.id === currentUser?.id ? (
                      <span className="muted">Tu cuenta</span>
                    ) : (
                      <button
                        type="button"
                        className="button-secondary"
                        disabled={updatingId === item.id}
                        onClick={() => void toggleActive(item)}
                      >
                        {item.is_active ? 'Deshabilitar' : 'Habilitar'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {data.items.length === 0 && (
                <tr>
                  <td colSpan={6} className="empty-row">
                    No se encontraron cuentas.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onChange={setPage} />
        </>
      )}
    </section>
  )
}
