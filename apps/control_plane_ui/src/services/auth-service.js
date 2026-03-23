import { persistToken, setState } from '../state/store.js';
import { apiClient } from './api-client.js';
import { logClientEvent } from './logger-service.js';

export const authService = {
  async login(username, password) {
    const session = await apiClient.post('/auth/login', { username, password }, { auth: false, retryable: false });
    window.localStorage.setItem('coreflow_admin_username', session.username);
    persistToken(session.access_token);
    setState({ session, lastError: null });
    logClientEvent('info', 'Administrator signed in', { username });
    return session;
  },
  async session() {
    const envelope = await apiClient.get('/auth/session', { retryable: false });
    if (envelope?.session?.username) {
      window.localStorage.setItem('coreflow_admin_username', envelope.session.username);
    }
    setState({ session: envelope.session, lastError: null });
    return envelope.session;
  },
  logout() {
    const username = window.localStorage.getItem('coreflow_admin_username') || 'unknown';
    persistToken('');
    setState({ session: null });
    logClientEvent('info', 'Administrator signed out', { username });
  },
};
