import mongoose, { Schema, Document } from 'mongoose';

export interface GpsData {
  latitude: number;
  longitude: number;
  speedKph?: number;
  satellites?: number;
  hdop?: number;
}

export interface SensorData {
  temperatureC?: number;
  humidityPct?: number;
  pressureHpa?: number;
  [key: string]: unknown;
}

export interface IotReading extends Document {
  deviceId: string;
  type: 'telemetry' | 'gps' | 'sensor';
  gps?: GpsData;
  sensors?: SensorData;
  createdAt: Date;
}

const GpsSchema = new Schema<GpsData>({
  latitude: { type: Number, required: true },
  longitude: { type: Number, required: true },
  speedKph: Number,
  satellites: Number,
  hdop: Number,
},{ _id: false });

const SensorSchema = new Schema<SensorData>({}, { strict: false, _id: false });

const ReadingSchema = new Schema<IotReading>({
  deviceId: { type: String, required: true, index: true },
  type: { type: String, enum: ['telemetry', 'gps', 'sensor'], default: 'telemetry' },
  gps: { type: GpsSchema, required: false },
  sensors: { type: SensorSchema, required: false },
  createdAt: { type: Date, default: Date.now, index: true },
});

ReadingSchema.index({ deviceId: 1, createdAt: -1 });

export const ReadingModel = mongoose.model<IotReading>('Reading', ReadingSchema);
