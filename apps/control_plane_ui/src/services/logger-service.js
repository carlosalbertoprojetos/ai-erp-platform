import { getState } from '../state/store.js';

let isSending = false;

export function logClientEvent(level, message, context = {}) {
  const normalizedLevel = String(level || 'info').toUpperCase();
  const payload = { level, message, context };
  const method = console[normalizedLevel.toLowerCase()] || console.log;
  method(`[CoreFlow UI] ${message}`, context);
  if (isSending || !getState().token) {
    return;
  }
  isSending = true;
  fetch('/api/control-plane/client-logs', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getState().token}`,
    },
    body: JSON.stringify(payload),
    keepalive: true,
  }).catch(() => undefined).finally(() => {
    isSending = false;
  });
}
