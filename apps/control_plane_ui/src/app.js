import { createAppShell } from './components/app-shell.js';
import { applyTheme } from './hooks/use-theme.js';
import { renderBillingPage } from './pages/billing-page.js';
import { renderDashboardPage } from './pages/dashboard-page.js';
import { renderLoginPage } from './pages/login-page.js';
import { renderModulesPage } from './pages/modules-page.js';
import { renderSystemHealthPage } from './pages/system-health-page.js';
import { renderTenantsPage } from './pages/tenants-page.js';
import { renderUsersRolesPage } from './pages/users-roles-page.js';
import { authService } from './services/auth-service.js';
import { getState, persistToken, setState, subscribe } from './state/store.js';

const routes = {
  '/login': renderLoginPage,
  '/dashboard': renderDashboardPage,
  '/tenants': renderTenantsPage,
  '/billing': renderBillingPage,
  '/system-health': renderSystemHealthPage,
  '/users-roles': renderUsersRolesPage,
  '/modules': renderModulesPage,
};

export function bootstrap(root) {
  let cleanup = () => {};
  let renderedRoute = '';
  const shell = createAppShell({ onNavigate: navigate, onLogout: logout });
  root.appendChild(shell.element);
  applyTheme();

  async function ensureSession() {
    if (!getState().token) {
      setState({ session: null, route: '/login' });
      return;
    }
    try {
      const session = await authService.session();
      setState({ session, route: getState().route === '/login' ? '/dashboard' : getState().route });
    } catch {
      persistToken('');
      setState({ session: null, route: '/login' });
    }
  }

  async function navigate(route, options = {}) {
    let nextRoute = routes[route] ? route : '/dashboard';
    if (!getState().session && nextRoute !== '/login') {
      nextRoute = '/login';
    }
    if (getState().session && nextRoute === '/login') {
      nextRoute = '/dashboard';
    }
    if (options.updateHash !== false && window.location.hash.replace('#', '') !== nextRoute) {
      window.location.hash = nextRoute;
      return;
    }
    setState({ route: nextRoute });
    if (renderedRoute === nextRoute && !options.forceRefresh) {
      return;
    }
    cleanup();
    cleanup = () => {};
    renderedRoute = nextRoute;
    const pageRenderer = routes[nextRoute] || renderDashboardPage;
    cleanup = (await pageRenderer({ shell })) || (() => {});
  }

  function logout() {
    authService.logout();
    renderedRoute = '';
    navigate('/login');
  }

  window.addEventListener('hashchange', () => {
    navigate(window.location.hash.replace('#', '') || '/dashboard', { updateHash: false });
  });

  window.addEventListener('coreflow:unauthorized', () => {
    persistToken('');
    setState({ session: null });
    renderedRoute = '';
    navigate('/login');
  });

  window.addEventListener('coreflow:login-success', async () => {
    await ensureSession();
    renderedRoute = '';
    navigate('/dashboard', { forceRefresh: true });
  });

  subscribe((state) => {
    shell.rerenderNav();
    shell.setGlobalLoading(state.loadingCount > 0);
  });

  ensureSession().then(() => navigate(getState().route, { updateHash: false, forceRefresh: true }));
}
