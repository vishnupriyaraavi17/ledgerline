export interface DatabaseHealth {
  status: 'connected' | 'disconnected';
  details?: string;
}

export interface HealthResponse {
  status: 'healthy' | 'degraded';
  app_name: string;
  version: string;
  environment: string;
  timestamp: string;
  database: DatabaseHealth;
}
