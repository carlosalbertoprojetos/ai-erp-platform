function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

export function statusPill(value) {
  return `<span class="status-pill status-${escapeHtml(String(value).toLowerCase().replace(/_/g, '-'))}">${escapeHtml(value)}</span>`;
}

export function statCard({ label, value, delta = '', tone = 'default' }) {
  return `<section class="stat-card stat-${tone}"><div class="stat-card__label">${escapeHtml(label)}</div><div class="stat-card__value">${escapeHtml(value)}</div><div class="stat-card__delta">${escapeHtml(delta)}</div></section>`;
}

export function sectionCard({ title, subtitle = '', actions = '', body = '' }) {
  return `<section class="section-card"><header class="section-card__header"><div><h2>${escapeHtml(title)}</h2><p>${escapeHtml(subtitle)}</p></div><div class="section-card__actions">${actions}</div></header><div class="section-card__body">${body}</div></section>`;
}

export function dataTable({ columns, rows, emptyMessage = 'No records found.' }) {
  if (!rows.length) {
    return `<div class="empty-state">${escapeHtml(emptyMessage)}</div>`;
  }
  const header = columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join('');
  const body = rows.map((row) => `<tr>${columns.map((column) => `<td>${row[column.key] ?? ''}</td>`).join('')}</tr>`).join('');
  return `<div class="table-shell"><table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table></div>`;
}

export function metricBar(points, formatter = (value) => String(value)) {
  if (!points.length) {
    return '<div class="empty-state">No metric data available.</div>';
  }
  const max = Math.max(...points.map((item) => item.value), 1);
  return `<div class="metric-bars">${points.map((item) => `<div class="metric-bar-row"><div class="metric-bar-row__label">${escapeHtml(item.label)}</div><div class="metric-bar-row__track"><span style="width:${Math.max((item.value / max) * 100, 8)}%"></span></div><div class="metric-bar-row__value">${escapeHtml(formatter(item.value, item.unit))}</div></div>`).join('')}</div>`;
}

export function tabs(items, activeId) {
  return `<div class="tabs">${items.map((item) => `<button class="tab-button ${item.id === activeId ? 'is-active' : ''}" data-tab="${escapeHtml(item.id)}">${escapeHtml(item.label)}</button>`).join('')}</div>`;
}

export function renderLoading(message = 'Loading data...') {
  return `<div class="loading-state"><div class="spinner"></div><div>${escapeHtml(message)}</div></div>`;
}

export function renderErrorState(title, error) {
  const message = error?.message || String(error || 'Unknown error.');
  const requestId = error?.requestId ? `<div class="error-meta">Request ID: ${escapeHtml(error.requestId)}</div>` : '';
  return `<div class="empty-state error-state"><strong>${escapeHtml(title)}</strong><p>${escapeHtml(message)}</p>${requestId}</div>`;
}

export function renderLoginCard(error = '') {
  return `
    <section class="login-card">
      <div class="login-card__hero">
        <div class="brand__mark">CF</div>
        <div>
          <h1>CoreFlow Control Plane</h1>
          <p>Sign in to manage tenants, billing, RBAC and platform health.</p>
        </div>
      </div>
      <form id="login-form" class="login-form">
        <label><span>Username</span><input name="username" autocomplete="username" required /></label>
        <label><span>Password</span><input name="password" type="password" autocomplete="current-password" required /></label>
        <button class="primary-button" type="submit">Sign in</button>
      </form>
      ${error ? `<div class="login-error">${escapeHtml(error)}</div>` : ''}
    </section>
  `;
}

export function formatCurrency(value, currency = 'USD') {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 0 }).format(Number(value || 0));
}

export function formatDate(value) {
  if (!value) {
    return '—';
  }
  return new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}

export function toast(container, message, tone = 'success') {
  container.innerHTML = `<div class="toast toast-${tone}">${escapeHtml(message)}</div>`;
  window.setTimeout(() => {
    if (container) {
      container.innerHTML = '';
    }
  }, 2600);
}

