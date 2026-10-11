import { useCallback, useEffect, useState } from 'react'

import { tasksService, type TaskInput } from '../../services/tasksService'
import type { Task, TaskStatus } from '../../types/task'
import TaskForm from './TaskForm'

const dueFormat = new Intl.DateTimeFormat('es-CL', { dateStyle: 'medium', timeStyle: 'short' })

const FILTERS: { id: TaskStatus; label: string }[] = [
  { id: 'pending', label: 'Pendientes' },
  { id: 'completed', label: 'Completadas' },
]

function isOverdue(task: Task): boolean {
  return task.status === 'pending' && task.due_at !== null && new Date(task.due_at) < new Date()
}

export default function TasksPanel() {
  const [tasks, setTasks] = useState<Task[] | null>(null)
  const [filter, setFilter] = useState<TaskStatus>('pending')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setTasks(await tasksService.list())
      setError(null)
    } catch {
      setError('No se pudieron cargar las tareas.')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function createTask(input: TaskInput) {
    await tasksService.create(input)
    setFilter('pending')
    await load()
  }

  async function saveTask(task: Task, input: TaskInput) {
    await tasksService.update(task.id, input)
    setEditingId(null)
    await load()
  }

  async function toggleCompleted(task: Task) {
    try {
      await tasksService.update(task.id, {
        status: task.status === 'pending' ? 'completed' : 'pending',
      })
      await load()
    } catch {
      setError('No se pudo actualizar la tarea.')
    }
  }

  async function removeTask(task: Task) {
    if (!window.confirm(`¿Seguro que quieres eliminar la tarea "${task.title}"?`)) return
    try {
      await tasksService.remove(task.id)
      await load()
    } catch {
      setError('No se pudo eliminar la tarea.')
    }
  }

  const visible = tasks?.filter((task) => task.status === filter) ?? []
  const counts = {
    pending: tasks?.filter((task) => task.status === 'pending').length ?? 0,
    completed: tasks?.filter((task) => task.status === 'completed').length ?? 0,
  }

  return (
    <section className="panel">
      <TaskForm submitLabel="Agregar" onSubmit={createTask} />

      <div className="tabs" role="tablist">
        {FILTERS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={item.id === filter}
            className={item.id === filter ? 'tab tab-active' : 'tab'}
            onClick={() => setFilter(item.id)}
          >
            {item.label} ({counts[item.id]})
          </button>
        ))}
      </div>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {tasks === null && !error && <p className="page-loading">Cargando…</p>}
      {tasks !== null && visible.length === 0 && (
        <p className="muted">
          {filter === 'pending' ? 'No tienes tareas pendientes.' : 'No hay tareas completadas.'}
        </p>
      )}

      <ul className="task-list">
        {visible.map((task) =>
          editingId === task.id ? (
            <li key={task.id}>
              <TaskForm
                task={task}
                submitLabel="Guardar"
                onSubmit={(input) => saveTask(task, input)}
                onCancel={() => setEditingId(null)}
              />
            </li>
          ) : (
            <li key={task.id} className="task-item">
              <input
                type="checkbox"
                checked={task.status === 'completed'}
                aria-label={`Marcar "${task.title}" como ${
                  task.status === 'pending' ? 'completada' : 'pendiente'
                }`}
                onChange={() => void toggleCompleted(task)}
              />
              <div className="task-body">
                <span
                  className={task.status === 'completed' ? 'task-title task-done' : 'task-title'}
                >
                  {task.title}
                </span>
                {task.description && <span className="muted">{task.description}</span>}
                {task.due_at && (
                  <span className={isOverdue(task) ? 'task-due task-overdue' : 'task-due'}>
                    {isOverdue(task) ? 'Vencida: ' : 'Vence: '}
                    {dueFormat.format(new Date(task.due_at))}
                  </span>
                )}
              </div>
              <span className="task-actions">
                <button
                  type="button"
                  className="button-secondary"
                  onClick={() => setEditingId(task.id)}
                >
                  Editar
                </button>
                <button
                  type="button"
                  className="button-secondary"
                  onClick={() => void removeTask(task)}
                >
                  Eliminar
                </button>
              </span>
            </li>
          ),
        )}
      </ul>
    </section>
  )
}
