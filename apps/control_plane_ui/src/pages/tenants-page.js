import { plansService } from '../services/plans-service.js';
import { tenantsService } from '../services/tenants-service.js';
import { dataTable, formatCurrency, formatDate, renderErrorState, renderLoading, sectionCard, statusPill, tabs, toast } from '../components/ui.js';

const tenantTabs = [
  { id: 'users', label: 'Users' },
  { id: 'billing', label: 'Billing' },
  { id: 'usage', label: 'Usage' },
  { id: 'settings', label: 'Settings' },
];

export async function renderTenantsPage({ shell }) {
  shell.setHeader('Tenants', 'Create tenants, assign plans and inspect operational posture.');
  shell.content.innerHTML = renderLoading('Loading tenants and plan catalog...');

  let selectedTenant = null;
  let activeTab = 'users';
  let plans = [];

  async function renderList() {
    const search = shell.content.querySelector('#tenant-search')?.value || '';
    const status = shell.content.querySelector('#tenant-status')?.value || '';
    try {
      const [tenantsResponse, fetchedPlans] = await Promise.all([
        tenantsService.list({ search, status, limit: 25, offset: 0 }),
        plansService.list(),
      ]);
      const tenants = tenantsResponse.items || [];
      plans = fetchedPlans;
      if (selectedTenant) {
        selectedTenant = await tenantsService.detail(selectedTenant.tenant.id);
      }
      const rows = tenants.map((tenant) => ({
        name: `<button class="inline-link" data-tenant-id="${tenant.id}">${tenant.name}</button>`,
        plan: tenant.plan,
        region: tenant.region,
        users: String(tenant.active_users),
        mrr: formatCurrency(tenant.monthly_recurring_revenue),
        status: statusPill(tenant.status),
      }));
      const detailHtml = selectedTenant ? renderDetail(selectedTenant) : '<div class="empty-state">Select or create a tenant to inspect details.</div>';
      shell.content.innerHTML = `
        ${sectionCard({
          title: 'Create tenant',
          subtitle: 'Bootstrap a new tenant and assign its initial plan.',
          body: `
            <form id="tenant-create-form" class="form-grid">
              <label><span>Name</span><input name="name" class="filter-input" placeholder="Acme Global" required /></label>
              <label><span>Slug</span><input name="slug" class="filter-input" placeholder="acme-global" required /></label>
              <label><span>Region</span><input name="region" class="filter-input" value="us-east-1" required /></label>
              <label><span>Billing email</span><input name="billing_email" type="email" class="filter-input" placeholder="billing@acme.test" required /></label>
              <label><span>Timezone</span><input name="timezone" class="filter-input" value="UTC" required /></label>
              <label><span>Locale</span><input name="locale" class="filter-input" value="en-US" required /></label>
              <label><span>Plan</span><select name="plan_key" class="filter-input">${plans.map((plan) => `<option value="${plan.key}">${plan.label} ? ${formatCurrency(plan.monthly_price, plan.currency)}</option>`).join('')}</select></label>
              <label class="checkbox-field"><input name="enforce_sso" type="checkbox" /><span>Enforce SSO</span></label>
              <div class="form-actions"><button type="submit" class="primary-button">Create tenant</button></div>
            </form>
          `,
        })}
        <div class="section-toolbar">
          <input id="tenant-search" class="filter-input" placeholder="Search tenants" value="${search}" />
          <select id="tenant-status" class="filter-input">
            <option value="">All statuses</option>
            <option value="active" ${status === 'active' ? 'selected' : ''}>Active</option>
            <option value="trialing" ${status === 'trialing' ? 'selected' : ''}>Trialing</option>
            <option value="churn_risk" ${status === 'churn_risk' ? 'selected' : ''}>Churn risk</option>
            <option value="suspended" ${status === 'suspended' ? 'selected' : ''}>Suspended</option>
          </select>
        </div>
        <div class="two-column-layout tenant-layout">
          ${sectionCard({ title: 'Tenant list', subtitle: `Current SaaS customer base ? ${tenantsResponse.total} total`, body: dataTable({ columns: [{ key: 'name', label: 'Tenant' }, { key: 'plan', label: 'Plan' }, { key: 'region', label: 'Region' }, { key: 'users', label: 'Users' }, { key: 'mrr', label: 'MRR' }, { key: 'status', label: 'Status' }], rows, emptyMessage: 'No tenants match the current filters.' }) })}
          ${sectionCard({ title: selectedTenant ? selectedTenant.tenant.name : 'Tenant detail', subtitle: selectedTenant ? `${selectedTenant.tenant.region} ? ${selectedTenant.tenant.plan}` : 'Users, billing, usage and settings', body: detailHtml })}
        </div>
      `;
      wireEvents();
    } catch (error) {
      shell.content.innerHTML = renderErrorState('Failed to load tenants.', error);
    }
  }

  function renderDetail(detail) {
    const usage = detail.usage;
    let body = '';
    if (activeTab === 'users') {
      body = dataTable({ columns: [{ key: 'name', label: 'Name' }, { key: 'email', label: 'Email' }, { key: 'role', label: 'Role' }, { key: 'status', label: 'Status' }, { key: 'last_active_at', label: 'Last Active' }], rows: detail.users.map((user) => ({ name: user.full_name, email: user.email, role: user.role, status: statusPill(user.status), last_active_at: formatDate(user.last_active_at) })), emptyMessage: 'No users assigned yet.' });
    }
    if (activeTab === 'billing') {
      body = `
        <div class="stack-list">
          <form id="assign-plan-form" class="inline-form" data-tenant-id="${detail.tenant.id}">
            <select name="plan_key" class="filter-input">${plans.map((plan) => `<option value="${plan.key}" ${plan.key === detail.tenant.plan ? 'selected' : ''}>${plan.label} ? ${formatCurrency(plan.monthly_price, plan.currency)}</option>`).join('')}</select>
            <select name="status" class="filter-input">
              <option value="active">Active</option>
              <option value="trialing" ${detail.tenant.status === 'trialing' ? 'selected' : ''}>Trialing</option>
              <option value="past_due">Past due</option>
            </select>
            <button type="submit" class="primary-button">Assign plan</button>
          </form>
          <div><strong>Subscriptions</strong>${dataTable({ columns: [{ key: 'plan', label: 'Plan' }, { key: 'status', label: 'Status' }, { key: 'amount', label: 'Monthly' }, { key: 'renewal', label: 'Renewal' }], rows: detail.subscriptions.map((item) => ({ plan: item.plan, status: statusPill(item.status), amount: formatCurrency(item.amount_monthly), renewal: formatDate(item.renewal_date) })), emptyMessage: 'No subscriptions found.' })}</div>
          <div><strong>Invoices</strong>${dataTable({ columns: [{ key: 'number', label: 'Invoice' }, { key: 'status', label: 'Status' }, { key: 'total', label: 'Total' }, { key: 'due', label: 'Due' }], rows: detail.invoices.map((item) => ({ number: item.number, status: statusPill(item.status), total: formatCurrency(item.total), due: formatDate(item.due_date) })), emptyMessage: 'No invoices found.' })}</div>
        </div>
      `;
    }
    if (activeTab === 'usage') {
      body = `<div class="key-value-grid"><div><span>API requests 24h</span><strong>${usage.api_requests_24h.toLocaleString()}</strong></div><div><span>Workflow runs 24h</span><strong>${usage.workflow_runs_24h.toLocaleString()}</strong></div><div><span>Storage</span><strong>${usage.storage_gb} GB</strong></div><div><span>Error rate</span><strong>${usage.error_rate_percent}%</strong></div></div>`;
    }
    if (activeTab === 'settings') {
      body = `<div class="key-value-grid"><div><span>Timezone</span><strong>${detail.settings.timezone}</strong></div><div><span>Locale</span><strong>${detail.settings.locale}</strong></div><div><span>Billing email</span><strong>${detail.settings.billing_email}</strong></div><div><span>Enforce SSO</span><strong>${detail.settings.enforce_sso ? 'Yes' : 'No'}</strong></div></div>`;
    }
    return `${tabs(tenantTabs, activeTab)}<div class="tab-panel">${body}</div>`;
  }

  function wireEvents() {
    shell.content.querySelector('#tenant-search')?.addEventListener('input', () => renderList());
    shell.content.querySelector('#tenant-status')?.addEventListener('change', () => renderList());
    shell.content.querySelectorAll('[data-tenant-id]').forEach((button) => {
      button.addEventListener('click', async () => {
        selectedTenant = await tenantsService.detail(button.dataset.tenantId);
        await renderList();
      });
    });
    shell.content.querySelectorAll('[data-tab]').forEach((button) => {
      button.addEventListener('click', () => {
        activeTab = button.dataset.tab;
        renderList();
      });
    });
    shell.content.querySelector('#tenant-create-form')?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const formData = new FormData(form);
      try {
        const created = await tenantsService.create({
          name: String(formData.get('name')),
          slug: String(formData.get('slug')),
          region: String(formData.get('region')),
          plan_key: String(formData.get('plan_key')),
          billing_email: String(formData.get('billing_email')),
          timezone: String(formData.get('timezone')),
          locale: String(formData.get('locale')),
          enforce_sso: formData.get('enforce_sso') === 'on',
        });
        selectedTenant = created;
        toast(shell.toastRegion, 'Tenant created successfully.');
        await renderList();
      } catch (error) {
        toast(shell.toastRegion, error.message, 'error');
      }
    });
    shell.content.querySelector('#assign-plan-form')?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const formData = new FormData(form);
      try {
        selectedTenant = await tenantsService.assignPlan(form.dataset.tenantId, String(formData.get('plan_key')), String(formData.get('status')));
        toast(shell.toastRegion, 'Plan assigned and billing updated.');
        await renderList();
      } catch (error) {
        toast(shell.toastRegion, error.message, 'error');
      }
    });
  }

  await renderList();
  return () => {};
}
