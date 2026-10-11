import type { Task, TaskStatus } from '../types/task'
import { apiFetch } from './apiClient'

export interface TaskInput {
  title: string
  description: string
  due_at: string | null
}

export const tasksService = {
  list: () => apiFetch<Task[]>('/tasks'),
  create: (input: TaskInput) =>
    apiFetch<Task>('/tasks', { method: 'POST', body: JSON.stringify(input) }),
  update: (taskId: string, changes: Partial<TaskInput> & { status?: TaskStatus }) =>
    apiFetch<Task>(`/tasks/${taskId}`, { method: 'PATCH', body: JSON.stringify(changes) }),
  remove: (taskId: string) => apiFetch<void>(`/tasks/${taskId}`, { method: 'DELETE' }),
}
