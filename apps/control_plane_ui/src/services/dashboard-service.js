import { apiClient } from './api-client.js';

export const dashboardService = {
  getSummary: () => apiClient.get('/dashboard'),
};
