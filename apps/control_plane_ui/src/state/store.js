const listeners = new Set();

const state = {
  route: window.location.hash.replace('#', '') || '/dashboard',
  token: localStorage.getItem('coreflow_admin_token') || '',
  theme: localStorage.getItem('coreflow_admin_theme') || 'dark',
  session: null,
  loadingCount: 0,
  lastError: null,
};

export function getState() {
  return state;
}

export function setState(patch) {
  Object.assign(state, patch);
  for (const listener of listeners) {
    listener(state);
  }
}

export function updateLoading(delta) {
  state.loadingCount = Math.max(state.loadingCount + delta, 0);
  setState({ loadingCount: state.loadingCount });
}

export function persistToken(token) {
  if (token) {
    localStorage.setItem('coreflow_admin_token', token);
  } else {
    localStorage.removeItem('coreflow_admin_token');
  }
  setState({ token });
}

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
