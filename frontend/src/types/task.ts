export type TaskStatus = 'pending' | 'completed'

export interface Task {
  id: string
  title: string
  description: string
  due_at: string | null
  status: TaskStatus
  created_at: string
  updated_at: string
}
