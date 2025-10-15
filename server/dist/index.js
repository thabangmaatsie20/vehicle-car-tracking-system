"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
require("dotenv/config");
const express_1 = __importDefault(require("express"));
const http_1 = __importDefault(require("http"));
const cors_1 = __importDefault(require("cors"));
const helmet_1 = __importDefault(require("helmet"));
const socket_io_1 = require("socket.io");
const mongoose_1 = __importDefault(require("mongoose"));
const mqtt_1 = __importDefault(require("mqtt"));
const Reading_1 = require("./models/Reading");
const deepseek_1 = require("./deepseek");
const PORT = parseInt(process.env.PORT || '8080', 10);
const API_KEY = process.env.API_KEY || '';
const MONGODB_URI = process.env.MONGODB_URI || 'mongodb://localhost:27017/iot_dashboard';
const MQTT_URL = process.env.MQTT_URL || 'mqtt://localhost:1883';
const MQTT_USERNAME = process.env.MQTT_USERNAME || undefined;
const MQTT_PASSWORD = process.env.MQTT_PASSWORD || undefined;
const MQTT_CLIENT_ID = process.env.MQTT_CLIENT_ID || 'server-bridge';
const MQTT_TELEMETRY_TOPIC = process.env.MQTT_TELEMETRY_TOPIC || 'iot/+/telemetry';
const MQTT_COMMAND_TOPIC_TEMPLATE = process.env.MQTT_COMMAND_TOPIC_TEMPLATE || 'iot/${deviceId}/commands';
const app = (0, express_1.default)();
app.use((0, helmet_1.default)());
app.use((0, cors_1.default)({ origin: true }));
app.use(express_1.default.json());
const httpServer = http_1.default.createServer(app);
const io = new socket_io_1.Server(httpServer, { cors: { origin: '*' } });
// Mongo
mongoose_1.default.connect(MONGODB_URI).then(() => {
    console.log('[Mongo] connected');
}).catch(err => {
    console.error('[Mongo] connection error', err);
    process.exit(1);
});
// MQTT
const mqttOptions = {
    clientId: MQTT_CLIENT_ID,
    username: MQTT_USERNAME,
    password: MQTT_PASSWORD,
    clean: true
};
const mqttClient = mqtt_1.default.connect(MQTT_URL, mqttOptions);
mqttClient.on('connect', () => {
    console.log('[MQTT] connected');
    mqttClient.subscribe(MQTT_TELEMETRY_TOPIC, (err) => {
        if (err)
            console.error('[MQTT] subscribe error', err);
        else
            console.log('[MQTT] subscribed', MQTT_TELEMETRY_TOPIC);
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
        const deviceId = data.deviceId || extractDeviceId(topic);
        const doc = new Reading_1.ReadingModel({
            deviceId,
            type: (data.type || 'telemetry'),
            gps: data.gps,
            sensors: data.sensors,
        });
        await doc.save();
        // Emit to all clients and to a room per device
        io.emit('telemetry', doc.toObject());
        io.to(roomForDevice(deviceId)).emit('telemetry', doc.toObject());
    }
    catch (err) {
        console.error('[MQTT] message handling error', err);
    }
});
function extractDeviceId(topic) {
    // topic example: iot/{deviceId}/telemetry
    const parts = topic.split('/');
    if (parts.length >= 3)
        return parts[1];
    return 'unknown';
}
function roomForDevice(deviceId) {
    return `device:${deviceId}`;
}
// Sockets
io.on('connection', (socket) => {
    console.log('[Socket] client connected', socket.id);
    socket.on('join-device', (deviceId) => {
        socket.join(roomForDevice(deviceId));
    });
    socket.on('disconnect', () => {
        console.log('[Socket] client disconnected', socket.id);
    });
});
// Auth middleware for API key protected routes
function requireApiKey(req, res, next) {
    const key = req.header('x-api-key');
    if (!API_KEY)
        return res.status(500).json({ error: 'Server missing API key' });
    if (key !== API_KEY)
        return res.status(401).json({ error: 'Unauthorized' });
    next();
}
// Routes
app.get('/api/health', (_req, res) => {
    res.json({ ok: true, time: new Date().toISOString() });
});
app.get('/api/readings', async (req, res) => {
    try {
        const deviceId = req.query.deviceId || 'pi-1';
        const limit = Math.min(parseInt(req.query.limit || '200', 10), 1000);
        const since = req.query.since ? new Date(parseInt(req.query.since, 10)) : undefined;
        const query = { deviceId };
        if (since)
            query.createdAt = { $gte: since };
        const results = await Reading_1.ReadingModel.find(query)
            .sort({ createdAt: -1 })
            .limit(limit)
            .lean();
        res.json(results);
    }
    catch (err) {
        res.status(500).json({ error: err.message || 'Failed to fetch readings' });
    }
});
app.post('/api/command', requireApiKey, (req, res) => {
    try {
        const { deviceId, command, payload } = req.body || {};
        if (!deviceId || !command)
            return res.status(400).json({ error: 'deviceId and command are required' });
        const topic = MQTT_COMMAND_TOPIC_TEMPLATE.replace('${deviceId}', deviceId);
        mqttClient.publish(topic, JSON.stringify({ command, payload, ts: Date.now() }));
        res.json({ ok: true });
    }
    catch (err) {
        res.status(500).json({ error: err.message || 'Failed to publish command' });
    }
});
app.post('/api/insights', requireApiKey, async (req, res) => {
    try {
        const { deviceId, fromTs, toTs, limit } = req.body || {};
        const apiKey = process.env.DEEPSEEK_API_KEY || '';
        if (!apiKey)
            return res.status(500).json({ error: 'Server missing DEEPSEEK_API_KEY' });
        const text = await (0, deepseek_1.getMovementInsights)({ deviceId, fromTs, toTs, limit, apiKey });
        res.json({ insight: text });
    }
    catch (err) {
        res.status(500).json({ error: err.message || 'Failed to generate insights' });
    }
});
httpServer.listen(PORT, () => {
    console.log(`[HTTP] listening on :${PORT}`);
});
