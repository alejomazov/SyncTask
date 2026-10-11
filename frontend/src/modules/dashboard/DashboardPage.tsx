import AgendaPanel from './AgendaPanel'
import TasksPanel from './TasksPanel'

export default function DashboardPage() {
  return (
    <>
      <h1>Panel</h1>
      <div className="dashboard-grid">
        <AgendaPanel />
        <TasksPanel />
      </div>
    </>
  )
}
