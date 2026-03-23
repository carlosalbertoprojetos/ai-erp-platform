import { getState } from '../state/store.js';
import { toggleTheme } from '../hooks/use-theme.js';

const navItems = [
  { id: '/dashboard', label: 'Dashboard' },
  { id: '/tenants', label: 'Tenants' },
  { id: '/billing', label: 'Billing' },
  { id: '/system-health', label: 'System Health' },
  { id: '/users-roles', label: 'Users & Roles' },
  { id: '/modules', label: 'Modules' },
];

export function createAppShell({ onNavigate, onLogout }) {
  const shell = document.createElement('div');
  shell.className = 'app-shell';
  shell.innerHTML = `
    <aside class="sidebar">
      <div class="brand">
        <div class="brand__mark">CF</div>
        <div>
          <div class="brand__title">CoreFlow</div>
          <div class="brand__subtitle">Control Plane</div>
        </div>
      </div>
      <nav class="nav"></nav>
      <div class="sidebar__footer">
        <div class="badge-live"></div>
      </div>
    </aside>
    <div class="workspace">
      <header class="topbar">
        <div>
          <h1 id="page-title">Control Plane</h1>
          <p id="page-subtitle">Platform operations and governance</p>
        </div>
        <div class="topbar__actions">
          <div class="session-chip" id="session-chip"></div>
          <button id="theme-toggle" class="ghost-button">Toggle theme</button>
          <button id="logout-button" class="ghost-button hidden">Logout</button>
        </div>
      </header>
      <div id="global-loading" class="global-loading hidden"><span></span></div>
      <div id="toast-region" class="toast-region"></div>
      <main id="page-content" class="page-content"></main>
    </div>
  `;

  const nav = shell.querySelector('.nav');
  const themeToggle = shell.querySelector('#theme-toggle');
  const logoutButton = shell.querySelector('#logout-button');
  const badge = shell.querySelector('.badge-live');
  const sessionChip = shell.querySelector('#session-chip');
  const loadingBar = shell.querySelector('#global-loading');

  themeToggle.addEventListener('click', () => toggleTheme());
  logoutButton.addEventListener('click', () => onLogout());

  function renderNav() {
    const state = getState();
    nav.innerHTML = state.session
      ? navItems.map((item) => `<button class="nav-link ${state.route === item.id ? 'is-active' : ''}" data-route="${item.id}">${item.label}</button>`).join('')
      : '';
    nav.querySelectorAll('[data-route]').forEach((button) => {
      button.addEventListener('click', () => {
        onNavigate(button.dataset.route);
      });
    });
    badge.textContent = `Live updates · ${new Date().toLocaleTimeString()}`;
    const session = state.session;
    sessionChip.textContent = session ? `${session.username} · ${session.scope}` : 'Authentication required';
    logoutButton.classList.toggle('hidden', !session);
  }

  renderNav();

  return {
    element: shell,
    content: shell.querySelector('#page-content'),
    toastRegion: shell.querySelector('#toast-region'),
    setHeader(title, subtitle) {
      shell.querySelector('#page-title').textContent = title;
      shell.querySelector('#page-subtitle').textContent = subtitle;
    },
    rerenderNav: renderNav,
    setGlobalLoading(active) {
      loadingBar.classList.toggle('hidden', !active);
    },
  };
}
