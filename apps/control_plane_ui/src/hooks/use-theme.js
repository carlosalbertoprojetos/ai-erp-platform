import { getState, setState } from '../state/store.js';

export function applyTheme() {
  document.documentElement.dataset.theme = getState().theme;
}

export function toggleTheme() {
  const nextTheme = getState().theme === 'dark' ? 'light' : 'dark';
  localStorage.setItem('coreflow_admin_theme', nextTheme);
  setState({ theme: nextTheme });
  applyTheme();
}
