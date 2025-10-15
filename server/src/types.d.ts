export type TelemetryPayload = {
  deviceId: string;
  type?: 'telemetry' | 'gps' | 'sensor';
  gps?: {
    latitude: number;
    longitude: number;
    speedKph?: number;
    satellites?: number;
    hdop?: number;
  };
  sensors?: Record<string, unknown>;
};
