import { renderErrorState, renderLoading, dataTable, sectionCard, statusPill, toast } from '../components/ui.js';
import { usersService } from '../services/users-service.js';

export async function renderUsersRolesPage({ shell }) {
  shell.setHeader('Users & Roles', 'Manage RBAC assignments and permission bundles across the platform.');
  shell.content.innerHTML = renderLoading('Loading users and roles...');

  async function render() {
    const search = shell.content.querySelector('#users-search')?.value || '';
    const selectedRole = shell.content.querySelector('#users-role-filter')?.value || '';
    try {
      const [usersResponse, roles] = await Promise.all([
        usersService.list({ search, role: selectedRole, limit: 25, offset: 0 }),
        usersService.roles(),
      ]);
      const users = usersResponse.items || [];
      shell.content.innerHTML = `
        <div class="section-toolbar">
          <input id="users-search" class="filter-input" placeholder="Search users" value="${search}" />
          <select id="users-role-filter" class="filter-input">
            <option value="">All roles</option>
            ${roles.map((role) => `<option value="${role.name}" ${selectedRole === role.name ? 'selected' : ''}>${role.name}</option>`).join('')}
          </select>
        </div>
        <div class="two-column-layout">
          ${sectionCard({ title: 'Assignments', subtitle: `${usersResponse.total} users in current scope`, body: dataTable({ columns: [{ key: 'name', label: 'Name' }, { key: 'email', label: 'Email' }, { key: 'role', label: 'Role' }, { key: 'status', label: 'Status' }, { key: 'action', label: 'Update' }], rows: users.map((user) => ({ name: user.full_name, email: user.email, role: `<select data-user-role="${user.id}" data-user-tenant="${user.tenant_id}" class="table-select">${roles.map((role) => `<option value="${role.name}" ${role.name === user.role ? 'selected' : ''}>${role.name}</option>`).join('')}</select>`, status: statusPill(user.status), action: `<button data-save-role="${user.id}" data-user-tenant="${user.tenant_id}" class="ghost-button">Save</button>` })) }) })}
          ${sectionCard({ title: 'Role Catalog', subtitle: 'Permission bundles available to admins', body: dataTable({ columns: [{ key: 'name', label: 'Role' }, { key: 'scope', label: 'Scope' }, { key: 'permissions', label: 'Permissions' }], rows: roles.map((role) => ({ name: role.name, scope: role.scope, permissions: role.permissions.join(', ') })) }) })}
        </div>
      `;
      wireEvents();
    } catch (error) {
      shell.content.innerHTML = renderErrorState('Failed to load users and roles.', error);
    }
  }

  function wireEvents() {
    shell.content.querySelector('#users-search')?.addEventListener('input', () => render());
    shell.content.querySelector('#users-role-filter')?.addEventListener('change', () => render());
    shell.content.querySelectorAll('[data-save-role]').forEach((button) => {
      button.addEventListener('click', async () => {
        const select = shell.content.querySelector(`[data-user-role="${button.dataset.saveRole}"]`);
        try {
          await usersService.updateRole(button.dataset.saveRole, select.value, button.dataset.userTenant || null);
          toast(shell.toastRegion, 'Role assignment updated.');
          render();
        } catch (error) {
          toast(shell.toastRegion, error.message, 'error');
        }
      });
    });
  }

  await render();
  return () => {};
}
