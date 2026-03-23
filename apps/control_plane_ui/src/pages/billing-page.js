import { billingService } from '../services/billing-service.js';
import { dataTable, formatCurrency, formatDate, renderErrorState, renderLoading, sectionCard, statCard, statusPill } from '../components/ui.js';

export async function renderBillingPage({ shell }) {
  shell.setHeader('Billing', 'Track subscriptions, invoices and revenue collection posture.');
  shell.content.innerHTML = renderLoading('Loading billing ledgers...');

  async function render() {
    const status = shell.content.querySelector('#billing-status')?.value || '';
    try {
      const overview = await billingService.overview(status);
      shell.content.innerHTML = `
        <div class="stats-grid">
          ${statCard({ label: 'Monthly Volume', value: formatCurrency(overview.monthly_volume), delta: 'Across all subscriptions', tone: 'accent' })}
          ${statCard({ label: 'Past Due Exposure', value: formatCurrency(overview.past_due_total), delta: 'Outstanding collections', tone: overview.past_due_total > 0 ? 'warning' : 'success' })}
        </div>
        <div class="section-toolbar">
          <select id="billing-status" class="filter-input">
            <option value="">All statuses</option>
            <option value="active" ${status === 'active' ? 'selected' : ''}>Active</option>
            <option value="trialing" ${status === 'trialing' ? 'selected' : ''}>Trialing</option>
            <option value="past_due" ${status === 'past_due' ? 'selected' : ''}>Past due</option>
            <option value="paid" ${status === 'paid' ? 'selected' : ''}>Paid</option>
            <option value="open" ${status === 'open' ? 'selected' : ''}>Open</option>
          </select>
        </div>
        <div class="two-column-layout">
          ${sectionCard({ title: 'Subscriptions', subtitle: 'Current active and transitional states', body: dataTable({ columns: [{ key: 'tenant_id', label: 'Tenant ID' }, { key: 'plan', label: 'Plan' }, { key: 'status', label: 'Status' }, { key: 'amount', label: 'Monthly' }, { key: 'renewal', label: 'Renewal' }], rows: overview.subscriptions.map((item) => ({ tenant_id: item.tenant_id.slice(0, 8), plan: item.plan, status: statusPill(item.status), amount: formatCurrency(item.amount_monthly), renewal: formatDate(item.renewal_date) })) }) })}
          ${sectionCard({ title: 'Invoices', subtitle: 'Recent invoice issuance and collection', body: dataTable({ columns: [{ key: 'number', label: 'Invoice' }, { key: 'tenant_id', label: 'Tenant ID' }, { key: 'status', label: 'Status' }, { key: 'total', label: 'Total' }, { key: 'due', label: 'Due' }], rows: overview.invoices.map((item) => ({ number: item.number, tenant_id: item.tenant_id.slice(0, 8), status: statusPill(item.status), total: formatCurrency(item.total), due: formatDate(item.due_date) })) }) })}
        </div>
      `;
      shell.content.querySelector('#billing-status')?.addEventListener('change', render);
    } catch (error) {
      shell.content.innerHTML = renderErrorState('Failed to load billing data.', error);
    }
  }

  await render();
  return () => {};
}
