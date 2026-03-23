import { updateLoading, getState } from '../state/store.js';
import { logClientEvent } from './logger-service.js';

const API_PREFIX = '/api/control-plane';
const RETRY_DELAYS_MS = [250, 600, 1200];

export class ApiError extends Error {
  constructor(message, status = 0, requestId = null, detail = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.requestId = requestId;
    this.detail = detail;
  }
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function parseError(response) {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    const payload = await response.json();
    return new ApiError(payload.detail || 'Request failed.', response.status, payload.request_id || response.headers.get('x-request-id'), payload);
  }
  const text = await response.text();
  return new ApiError(text || 'Request failed.', response.status, response.headers.get('x-request-id'));
}

async function request(path, options = {}) {
  const retryable = options.retryable !== false;
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };
  if (options.auth !== false && getState().token) {
    headers.Authorization = `Bearer ${getState().token}`;
  }

  updateLoading(1);
  try {
    for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt += 1) {
      try {
        const response = await fetch(`${API_PREFIX}${path}`, {
          ...options,
          headers,
        });
        if (response.ok) {
          if (response.status === 204) {
            return null;
          }
          const contentType = response.headers.get('content-type') || '';
          return contentType.includes('application/json') ? response.json() : response.text();
        }
        const apiError = await parseError(response);
        if (apiError.status === 401) {
          window.dispatchEvent(new CustomEvent('coreflow:unauthorized', { detail: apiError }));
          throw apiError;
        }
        if (!retryable || (apiError.status < 500 && apiError.status !== 429) || attempt === RETRY_DELAYS_MS.length) {
          throw apiError;
        }
        logClientEvent('warn', 'Retrying failed API request', { path, attempt: attempt + 1, status: apiError.status });
      } catch (error) {
        const apiError = error instanceof ApiError ? error : new ApiError(error.message || 'Network error.', 0);
        if (!retryable || (apiError.status && apiError.status < 500 && apiError.status !== 429) || attempt === RETRY_DELAYS_MS.length) {
          logClientEvent('error', 'API request failed', { path, status: apiError.status, detail: apiError.detail || apiError.message });
          throw apiError;
        }
        await sleep(RETRY_DELAYS_MS[attempt]);
      }
    }
  } finally {
    updateLoading(-1);
  }
  throw new ApiError('Unexpected client request failure.');
}

export const apiClient = {
  get: (path, options = {}) => request(path, { ...options, method: 'GET' }),
  post: (path, body, options = {}) => request(path, { ...options, method: 'POST', body: JSON.stringify(body) }),
  put: (path, body, options = {}) => request(path, { ...options, method: 'PUT', body: JSON.stringify(body) }),
  patch: (path, body, options = {}) => request(path, { ...options, method: 'PATCH', body: JSON.stringify(body) }),
};
