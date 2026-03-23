import { dashboardService } from '../services/dashboard-service.js';
import { usePolling } from '../hooks/use-polling.js';
import { formatCurrency, metricBar, renderErrorState, renderLoading, sectionCard, statCard, statusPill } from '../components/ui.js';

export async function renderDashboardPage({ shell }) {
  shell.setHeader('Executive Dashboard', 'MRR, tenant activity, execution errors and global platform health.');
  shell.content.innerHTML = renderLoading('Loading executive metrics...');

  const render = async () => {
    try {
      const data = await dashboardService.getSummary();
      shell.content.innerHTML = `
        <div class="stats-grid">
          ${statCard({ label: 'MRR', value: formatCurrency(data.mrr), delta: `${data.mrr_delta_percent}% vs last month`, tone: 'accent' })}
          ${statCard({ label: 'Active Tenants', value: String(data.active_tenants), delta: `${data.tenant_growth_percent}% growth`, tone: 'success' })}
          ${statCard({ label: 'Open Errors', value: String(data.open_errors), delta: 'Requires operator attention', tone: data.open_errors > 0 ? 'warning' : 'success' })}
          ${statCard({ label: 'System Health', value: `${data.system_health_score}/100`, delta: data.system_health, tone: data.system_health === 'healthy' ? 'success' : 'warning' })}
        </div>
        <div class="two-column-layout">
          ${sectionCard({ title: 'Revenue by plan', subtitle: 'Current recurring revenue split', body: metricBar(data.revenue_series, (value) => formatCurrency(value)) })}
          ${sectionCard({ title: 'Tenant distribution', subtitle: 'Tenant footprint by region', body: metricBar(data.tenant_distribution, (value, unit) => `${value} ${unit}`) })}
        </div>
        ${sectionCard({ title: 'Platform posture', subtitle: 'Current control-plane operating state', body: `<div class="health-banner">${statusPill(data.system_health)} <span>Control plane is running with ${data.open_errors} open execution errors.</span></div>` })}
      `;
    } catch (error) {
      shell.content.innerHTML = renderErrorState('Failed to load dashboard.', error);
    }
  };

  const stopPolling = usePolling(render, 12000);
  return () => stopPolling();
}
