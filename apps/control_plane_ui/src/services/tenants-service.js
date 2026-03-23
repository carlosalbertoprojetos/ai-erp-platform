import { apiClient } from './api-client.js';

export const tenantsService = {
  list: (params = {}) => {
    const search = new URLSearchParams();
    if (params.search) search.set('search', params.search);
    if (params.status) search.set('status', params.status);
    if (params.limit) search.set('limit', String(params.limit));
    if (params.offset) search.set('offset', String(params.offset));
    const query = search.toString();
    return apiClient.get(`/tenants${query ? `?${query}` : ''}`);
  },
  detail: (tenantId) => apiClient.get(`/tenants/${tenantId}`),
  create: (payload, idempotencyKey = crypto.randomUUID()) =>
    apiClient.post('/tenants', payload, { headers: { 'Idempotency-Key': idempotencyKey } }),
  assignPlan: (tenantId, planKey, status = 'active', idempotencyKey = crypto.randomUUID()) =>
    apiClient.patch(`/tenants/${tenantId}/plan`, { plan_key: planKey, status }, { headers: { 'Idempotency-Key': idempotencyKey } }),
};
