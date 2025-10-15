## IoT Dashboard (Raspberry Pi 4 + MQTT + MongoDB + React)

### 1) Tech stack
- **Frontend**: React + Vite, Leaflet.js (map), Socket.IO client
- **Backend**: Node.js (Express), Socket.IO, MongoDB (Mongoose), MQTT bridge
- **Communication**: MQTT topics `iot/{deviceId}/telemetry`, `iot/{deviceId}/commands`
- **AI**: DeepSeek Chat Completions API for movement insights

### 2) Architecture
```
[Raspberry Pi 4]
  - publisher.py (GPS Neo-6M via serial, other sensors) -> MQTT (iot/{deviceId}/telemetry)
  - listens to MQTT (iot/{deviceId}/commands)

[MQTT Broker]
  - Mosquitto (docker-compose) or cloud MQTT

[Backend]
  - Express REST API (/api/readings, /api/command, /api/insights)
  - MQTT client subscribes to telemetry, saves to MongoDB
  - Socket.IO broadcasts live telemetry to dashboard

[MongoDB]
  - Stores documents per reading

[React Dashboard]
  - Live Leaflet map, sensor cards, command buttons
  - Calls API and listens via Socket.IO
```

### 3) Local setup
- Requirements: Docker, Node 18+, pnpm or npm, Python 3 (for Pi only)

```bash
# Start MongoDB and Mosquitto locally
docker compose up -d

# Server
cd server
cp .env.example .env
# Edit .env, set API_KEY and DEEPSEEK_API_KEY
pnpm install   # or npm install
pnpm dev       # or npm run dev

# Web
cd ../web
pnpm install
# point VITE_API_BASE to your server in .env.local (optional)
pnpm dev
```

`.env` (server):
```
PORT=8080
API_KEY=change-me-strong-key
MONGODB_URI=mongodb://localhost:27017/iot_dashboard
MQTT_URL=mqtt://localhost:1883
MQTT_USERNAME=
MQTT_PASSWORD=
MQTT_CLIENT_ID=server-bridge
MQTT_TELEMETRY_TOPIC=iot/+/telemetry
MQTT_COMMAND_TOPIC_TEMPLATE=iot/${deviceId}/commands
DEEPSEEK_API_KEY=sk-... # your key
DEEPSEEK_MODEL=deepseek-chat
```

`.env.local` (web, optional):
```
VITE_API_BASE=http://localhost:8080
```

### 4) Raspberry Pi script
```bash
# On the Pi
sudo raspi-config # enable serial / disable login shell on serial
python3 -m venv venv && source venv/bin/activate
pip install -r pi/requirements.txt
export DEVICE_ID=pi-1
export MQTT_HOST=<broker-ip-or-hostname>
export MQTT_PORT=1883
python pi/publisher.py
```

If you don't have a GPS fix yet, the script still publishes with `gps=null` until data arrives.

### 5) Deploy
- Backend: Render/Fly/EC2/Droplet. Expose port 8080, set environment variables.
- Frontend: Netlify/Vercel/Cloudflare Pages; set `VITE_API_BASE` to your backend URL.
- Use a managed MongoDB (MongoDB Atlas) and managed MQTT if preferred.

### 6) Security
- Protect command/insight endpoints using `x-api-key` (set `API_KEY`).
- For production, disable anonymous MQTT and add username/password/TLS in Mosquitto.
- Consider JWT auth and per-device ACLs as you scale.

### 7) DeepSeek insights
- POST `/api/insights` with body `{ deviceId, limit }` and header `x-api-key: <API_KEY>`.
- The backend summarizes recent GPS points for anomalies.

### 8) Notes
- Map uses OpenStreetMap tiles. Swap to Google Maps if desired.
- Extend schema in `server/src/models/Reading.ts` for more sensors.
- Command examples: `ping`, `blink-led` (implement GPIO on Pi).
