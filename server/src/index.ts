import 'dotenv/config';
import express from 'express';
import http from 'http';
import cors from 'cors';
import helmet from 'helmet';
import { Server as SocketIOServer } from 'socket.io';
import mongoose from 'mongoose';
import mqtt, { IClientOptions } from 'mqtt';
import { ReadingModel } from './models/Reading';
import { getMovementInsights } from './deepseek';

const PORT = parseInt(process.env.PORT || '8080', 10);
const API_KEY = process.env.API_KEY || '';
const MONGODB_URI = process.env.MONGODB_URI || 'mongodb://localhost:27017/iot_dashboard';
const MQTT_URL = process.env.MQTT_URL || 'mqtt://localhost:1883';
const MQTT_USERNAME = process.env.MQTT_USERNAME || undefined;
const MQTT_PASSWORD = process.env.MQTT_PASSWORD || undefined;
const MQTT_CLIENT_ID = process.env.MQTT_CLIENT_ID || 'server-bridge';
const MQTT_TELEMETRY_TOPIC = process.env.MQTT_TELEMETRY_TOPIC || 'iot/+/telemetry';
const MQTT_COMMAND_TOPIC_TEMPLATE = process.env.MQTT_COMMAND_TOPIC_TEMPLATE || 'iot/${deviceId}/commands';

const app = express();
app.use(helmet());
app.use(cors({ origin: true }));
app.use(express.json());

const httpServer = http.createServer(app);
const io = new SocketIOServer(httpServer, { cors: { origin: '*' } });

// Mongo
mongoose.connect(MONGODB_URI).then(() => {
  console.log('[Mongo] connected');
}).catch(err => {
  console.error('[Mongo] connection error', err);
  process.exit(1);
});

// MQTT
const mqttOptions: IClientOptions = {
  clientId: MQTT_CLIENT_ID,
  username: MQTT_USERNAME,
  password: MQTT_PASSWORD,
  clean: true
};

const mqttClient = mqtt.connect(MQTT_URL, mqttOptions);

mqttClient.on('connect', () => {
  console.log('[MQTT] connected');
  mqttClient.subscribe(MQTT_TELEMETRY_TOPIC, (err) => {
    if (err) console.error('[MQTT] subscribe error', err);
    else console.log('[MQTT] subscribed', MQTT_TELEMETRY_TOPIC);
  });
});

mqttClient.on('error', (err) => {
  console.error('[MQTT] error', err);
});

mqttClient.on('message', async (topic, payload) => {
  try {
    const text = payload.toString('utf8');
    const data = JSON.parse(text);
    // Expect { deviceId, gps?, sensors?, type? }
    const deviceId: string = data.deviceId || extractDeviceId(topic);

    const doc = new ReadingModel({
      deviceId,
      type: (data.type || 'telemetry'),
      gps: data.gps,
      sensors: data.sensors,
    });

    await doc.save();

    // Emit to all clients and to a room per device
    io.emit('telemetry', doc.toObject());
    io.to(roomForDevice(deviceId)).emit('telemetry', doc.toObject());
  } catch (err) {
    console.error('[MQTT] message handling error', err);
  }
});

function extractDeviceId(topic: string): string {
  // topic example: iot/{deviceId}/telemetry
  const parts = topic.split('/');
  if (parts.length >= 3) return parts[1];
  return 'unknown';
}

function roomForDevice(deviceId: string) {
  return `device:${deviceId}`;
}

// Sockets
io.on('connection', (socket) => {
  console.log('[Socket] client connected', socket.id);

  socket.on('join-device', (deviceId: string) => {
    socket.join(roomForDevice(deviceId));
  });

  socket.on('disconnect', () => {
    console.log('[Socket] client disconnected', socket.id);
  });
});

// Auth middleware for API key protected routes
function requireApiKey(req: express.Request, res: express.Response, next: express.NextFunction) {
  const key = req.header('x-api-key');
  if (!API_KEY) return res.status(500).json({ error: 'Server missing API key' });
  if (key !== API_KEY) return res.status(401).json({ error: 'Unauthorized' });
  next();
}

// Routes
app.get('/api/health', (_req, res) => {
  res.json({ ok: true, time: new Date().toISOString() });
});

app.get('/api/readings', async (req, res) => {
  try {
    const deviceId = (req.query.deviceId as string) || 'pi-1';
    const limit = Math.min(parseInt((req.query.limit as string) || '200', 10), 1000);
    const since = req.query.since ? new Date(parseInt(req.query.since as string, 10)) : undefined;

    const query: any = { deviceId };
    if (since) query.createdAt = { $gte: since };

    const results = await ReadingModel.find(query)
      .sort({ createdAt: -1 })
      .limit(limit)
      .lean();

    res.json(results);
  } catch (err: any) {
    res.status(500).json({ error: err.message || 'Failed to fetch readings' });
  }
});

app.post('/api/command', requireApiKey, (req, res) => {
  try {
    const { deviceId, command, payload } = req.body || {};
    if (!deviceId || !command) return res.status(400).json({ error: 'deviceId and command are required' });
    const topic = MQTT_COMMAND_TOPIC_TEMPLATE.replace('${deviceId}', deviceId);
    mqttClient.publish(topic, JSON.stringify({ command, payload, ts: Date.now() }));
    res.json({ ok: true });
  } catch (err: any) {
    res.status(500).json({ error: err.message || 'Failed to publish command' });
  }
});

app.post('/api/insights', requireApiKey, async (req, res) => {
  try {
    const { deviceId, fromTs, toTs, limit } = req.body || {};
    const apiKey = process.env.DEEPSEEK_API_KEY || '';
    if (!apiKey) return res.status(500).json({ error: 'Server missing DEEPSEEK_API_KEY' });

    const text = await getMovementInsights({ deviceId, fromTs, toTs, limit, apiKey });
    res.json({ insight: text });
  } catch (err: any) {
    res.status(500).json({ error: err.message || 'Failed to generate insights' });
  }
});

httpServer.listen(PORT, () => {
  console.log(`[HTTP] listening on :${PORT}`);
});
