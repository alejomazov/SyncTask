import { useState, type FormEvent } from 'react'

import type { TaskInput } from '../../services/tasksService'
import type { Task } from '../../types/task'

const MAX_TITLE_LENGTH = 200

/** Converts an ISO instant to the value expected by a datetime-local input (local time). */
function toLocalInputValue(iso: string | null): string {
  if (!iso) return ''
  const date = new Date(iso)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

interface TaskFormProps {
  /** Task being edited; omit to create a new one. */
  task?: Task
  submitLabel: string
  onSubmit: (input: TaskInput) => Promise<void>
  onCancel?: () => void
}

export default function TaskForm({ task, submitLabel, onSubmit, onCancel }: TaskFormProps) {
  const [title, setTitle] = useState(task?.title ?? '')
  const [description, setDescription] = useState(task?.description ?? '')
  const [dueAt, setDueAt] = useState(toLocalInputValue(task?.due_at ?? null))
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!title.trim()) {
      setError('La tarea necesita un título.')
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      await onSubmit({
        title: title.trim(),
        description: description.trim(),
        due_at: dueAt ? new Date(dueAt).toISOString() : null,
      })
      if (!task) {
        setTitle('')
        setDescription('')
        setDueAt('')
      }
    } catch {
      setError('No se pudo guardar la tarea.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="task-form" onSubmit={handleSubmit}>
      <input
        type="text"
        placeholder="Nueva tarea"
        aria-label="Título de la tarea"
        maxLength={MAX_TITLE_LENGTH}
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <textarea
        placeholder="Descripción (opcional)"
        aria-label="Descripción"
        rows={2}
        maxLength={2000}
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <div className="task-form-row">
        <label>
          Fecha límite
          <input type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)} />
        </label>
        <span className="task-form-actions">
          {onCancel && (
            <button type="button" className="button-secondary" onClick={onCancel}>
              Cancelar
            </button>
          )}
          <button type="submit" disabled={submitting}>
            {submitLabel}
          </button>
        </span>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </form>
  )
}
