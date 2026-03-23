import { apiClient } from './api-client.js';

export const billingService = {
  overview: (status = '') => apiClient.get(`/billing${status ? `?status=${encodeURIComponent(status)}` : ''}`),
};
