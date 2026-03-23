import { usePolling } from '../hooks/use-polling.js';
import { healthService } from '../services/health-service.js';
import { dataTable, formatDate, renderErrorState, renderLoading, sectionCard, statCard, statusPill } from '../components/ui.js';

export async function renderSystemHealthPage({ shell }) {
  shell.setHeader('System Health', 'Operational telemetry, alerts and execution logs in real time.');
  shell.content.innerHTML = renderLoading('Loading platform telemetry...');

  const render = async () => {
    try {
      const data = await healthService.summary();
      const queueDepth = data.metrics.find((item) => item.label === 'queue_depth')?.value ?? 0;
      const activeJobs = data.metrics.find((item) => item.label === 'active_jobs')?.value ?? 0;
      const errorRuns = data.metrics.find((item) => item.label === 'error_runs')?.value ?? 0;
      shell.content.innerHTML = `
        <div class="stats-grid">
          ${statCard({ label: 'Health State', value: data.status.toUpperCase(), delta: 'Current platform posture', tone: data.status === 'healthy' ? 'success' : 'warning' })}
          ${statCard({ label: 'Queue Depth', value: String(queueDepth), delta: 'Pending jobs', tone: queueDepth > 0 ? 'warning' : 'default' })}
          ${statCard({ label: 'Active Jobs', value: String(activeJobs), delta: 'Workers in flight', tone: 'accent' })}
          ${statCard({ label: 'Error Runs', value: String(errorRuns), delta: 'Execution failures recorded', tone: errorRuns > 0 ? 'warning' : 'success' })}
        </div>
        <div class="two-column-layout">
          ${sectionCard({ title: 'Alerts', subtitle: 'Actionable incidents and warnings', body: dataTable({ columns: [{ key: 'severity', label: 'Severity' }, { key: 'source', label: 'Source' }, { key: 'message', label: 'Message' }, { key: 'created_at', label: 'Created' }], rows: data.alerts.map((item) => ({ severity: statusPill(item.severity), source: item.source, message: item.message, created_at: formatDate(item.created_at) })), emptyMessage: 'No active alerts.' }) })}
          ${sectionCard({ title: 'Recent Logs', subtitle: 'Most recent execution-plane log lines', body: dataTable({ columns: [{ key: 'level', label: 'Level' }, { key: 'source', label: 'Source' }, { key: 'message', label: 'Message' }, { key: 'created_at', label: 'Created' }], rows: data.logs.map((item) => ({ level: statusPill(item.level), source: item.source, message: item.message, created_at: formatDate(item.created_at) })), emptyMessage: 'No logs found.' }) })}
        </div>
      `;
    } catch (error) {
      shell.content.innerHTML = renderErrorState('Failed to load system health.', error);
    }
  };

  const stopPolling = usePolling(render, 10000);
  return () => stopPolling();
}
