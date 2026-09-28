import { ChatPage } from '../features/chat/pages/ChatPage'
import { DocumentsPage } from '../features/documents/pages/DocumentsPage'
import { TenantsPage } from '../features/tenants/pages/TenantsPage'
import { DashboardPage } from '../features/dashboard/pages/DashboardPage'
import { UsersPage } from '../features/users/pages/UsersPage'

export const routes = [
  { path: '/chat', label: 'Chat', element: ChatPage, roles: ['TENANT_ADMIN', 'USER'] },
  { path: '/dashboard', label: 'Dashboard', element: DashboardPage, roles: ['PLATFORM_ADMIN', 'TENANT_ADMIN'] },
  { path: '/documents', label: 'Documents', element: DocumentsPage, roles: ['TENANT_ADMIN'] },
  { path: '/users', label: 'Users', element: UsersPage, roles: ['PLATFORM_ADMIN', 'TENANT_ADMIN'] },
  { path: '/tenants', label: 'Tenants', element: TenantsPage, roles: ['PLATFORM_ADMIN'] },
]
