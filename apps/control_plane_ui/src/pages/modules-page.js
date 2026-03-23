import { dataTable, renderErrorState, renderLoading, sectionCard, toast } from '../components/ui.js';
import { modulesService } from '../services/modules-service.js';
import { tenantsService } from '../services/tenants-service.js';

export async function renderModulesPage({ shell }) {
  shell.setHeader('Modules & Feature Flags', 'Control tenant entitlements, module rollout and platform experiments.');
  shell.content.innerHTML = renderLoading('Loading feature flags...');

  async function render() {
    const selectedTenant = shell.content.querySelector('#module-tenant-filter')?.value || '';
    try {
      const [tenantsResponse, modulesResponse] = await Promise.all([
        tenantsService.list({ limit: 100, offset: 0 }),
        modulesService.list(selectedTenant, { limit: 100, offset: 0 }),
      ]);
      const tenants = tenantsResponse.items || [];
      const modules = modulesResponse.items || [];
      shell.content.innerHTML = `
        <div class="section-toolbar">
          <select id="module-tenant-filter" class="filter-input">
            <option value="">All tenants</option>
            ${tenants.map((tenant) => `<option value="${tenant.id}" ${selectedTenant === tenant.id ? 'selected' : ''}>${tenant.name}</option>`).join('')}
          </select>
        </div>
        ${sectionCard({ title: 'Feature flag matrix', subtitle: `${modulesResponse.total} module assignments`, body: dataTable({ columns: [{ key: 'label', label: 'Module' }, { key: 'category', label: 'Category' }, { key: 'tenant_id', label: 'Tenant' }, { key: 'enabled', label: 'Enabled' }, { key: 'rollout', label: 'Rollout' }, { key: 'action', label: 'Apply' }], rows: modules.map((item) => ({ label: item.label, category: item.category, tenant_id: item.tenant_id ? item.tenant_id.slice(0, 8) : 'global', enabled: `<input type="checkbox" data-module-enabled="${item.id}" ${item.enabled ? 'checked' : ''} />`, rollout: `<input type="range" min="0" max="100" value="${item.rollout}" data-module-rollout="${item.id}" /> <span class="range-value">${item.rollout}%</span>`, action: `<button data-module-save="${item.id}" data-module-tenant="${item.tenant_id || ''}" class="ghost-button">Save</button>` })) }) })}
      `;
      wireEvents();
    } catch (error) {
      shell.content.innerHTML = renderErrorState('Failed to load module flags.', error);
    }
  }

  function wireEvents() {
    shell.content.querySelector('#module-tenant-filter')?.addEventListener('change', () => render());
    shell.content.querySelectorAll('[data-module-rollout]').forEach((input) => {
      input.addEventListener('input', () => {
        const valueNode = input.parentElement.querySelector('.range-value');
        valueNode.textContent = `${input.value}%`;
      });
    });
    shell.content.querySelectorAll('[data-module-save]').forEach((button) => {
      button.addEventListener('click', async () => {
        const enabled = shell.content.querySelector(`[data-module-enabled="${button.dataset.moduleSave}"]`).checked;
        const rollout = Number(shell.content.querySelector(`[data-module-rollout="${button.dataset.moduleSave}"]`).value);
        try {
          await modulesService.update(button.dataset.moduleSave, enabled, rollout, button.dataset.moduleTenant || null);
          toast(shell.toastRegion, 'Module flag updated.');
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
