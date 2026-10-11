import { useState } from 'react'

import AuditLogTab from './AuditLogTab'
import ConnectionsTab from './ConnectionsTab'
import UsersTab from './UsersTab'

const TABS = [
  { id: 'users', label: 'Cuentas', component: UsersTab },
  { id: 'connections', label: 'Conexiones', component: ConnectionsTab },
  { id: 'audit', label: 'Auditoría', component: AuditLogTab },
] as const

type TabId = (typeof TABS)[number]['id']

export default function AdminPage() {
  const [activeTab, setActiveTab] = useState<TabId>('users')
  const ActiveComponent = TABS.find((tab) => tab.id === activeTab)!.component

  return (
    <>
      <h1>Administración</h1>
      <div className="tabs" role="tablist">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={tab.id === activeTab}
            className={tab.id === activeTab ? 'tab tab-active' : 'tab'}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        <ActiveComponent />
      </div>
    </>
  )
}
