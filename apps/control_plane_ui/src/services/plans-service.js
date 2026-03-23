import { apiClient } from './api-client.js';

export const plansService = {
  list: () => apiClient.get('/plans'),
};
