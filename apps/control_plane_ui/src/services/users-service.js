import { apiClient } from './api-client.js';

export const usersService = {
  list: (params = {}) => {
    const search = new URLSearchParams();
    if (params.search) search.set('search', params.search);
    if (params.role) search.set('role', params.role);
    if (params.limit) search.set('limit', String(params.limit));
    if (params.offset) search.set('offset', String(params.offset));
    if (params.tenantId) search.set('tenant_id', params.tenantId);
    const query = search.toString();
    return apiClient.get(`/users${query ? `?${query}` : ''}`);
  },
  roles: () => apiClient.get('/roles'),
  updateRole: (userId, role, tenantId = null) =>
    apiClient.patch(`/users/${userId}/role`, { role }, tenantId ? { headers: { 'X-Tenant-Id': tenantId } } : {}),
  upsertRole: (payload) => apiClient.put('/roles', payload),
};
