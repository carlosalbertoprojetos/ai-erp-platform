import { apiClient } from './api-client.js';

export const healthService = {
  summary: () => apiClient.get('/system-health'),
};
