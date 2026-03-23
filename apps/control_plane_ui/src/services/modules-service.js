import { apiClient } from './api-client.js';

export const modulesService = {
  list: (tenantId = '', options = {}) => {
    const params = new URLSearchParams();
    if (tenantId) params.set('tenant_id', tenantId);
    if (options.limit) params.set('limit', String(options.limit));
    if (options.offset) params.set('offset', String(options.offset));
    const query = params.toString();
    return apiClient.get(`/modules${query ? `?${query}` : ''}`);
  },
  update: (moduleId, enabled, rollout, tenantId = null) =>
    apiClient.patch(`/modules/${moduleId}`, { enabled, rollout }, tenantId ? { headers: { 'X-Tenant-Id': tenantId } } : {}),
};
