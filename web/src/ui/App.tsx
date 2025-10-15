import React, { useEffect, useMemo, useRef, useState } from 'react';
import { io, Socket } from 'socket.io-client';
import { MapContainer, TileLayer, Marker, Polyline, Popup } from 'react-leaflet';
import L from 'leaflet';

const API_BASE: string = (import.meta as any).env?.VITE_API_BASE || 'http://localhost:8080';
const SOCKET_URL = API_BASE;

const markerIcon = new L.Icon({
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  shadowSize: [41, 41]
});

function useSocket(deviceId: string) {
  const socketRef = useRef<Socket | null>(null);

  useEffect(() => {
    const socket = io(SOCKET_URL, { transports: ['websocket'] });
    socketRef.current = socket;
    socket.emit('join-device', deviceId);
    return () => { socket.disconnect(); };
  }, [deviceId]);

  return socketRef;
}

export default function App() {
  const [deviceId, setDeviceId] = useState('pi-1');
  const [apiKey, setApiKey] = useState('');
  const [latestGps, setLatestGps] = useState<{ lat: number, lon: number, speedKph?: number } | null>(null);
  const [path, setPath] = useState<[number, number][]>([]);
  const [temp, setTemp] = useState<number | null>(null);
  const [humidity, setHumidity] = useState<number | null>(null);
  const [insight, setInsight] = useState<string>('');

  const socketRef = useSocket(deviceId);

  useEffect(() => {
    async function loadHistory() {
      const resp = await fetch(`${API_BASE}/api/readings?deviceId=${encodeURIComponent(deviceId)}&limit=200`);
      const data = await resp.json();
      const coords: [number, number][] = [];
      for (const r of data.reverse()) {
        if (r.gps?.latitude && r.gps?.longitude) {
          coords.push([r.gps.latitude, r.gps.longitude]);
        }
      }
      setPath(coords);
      const last = data.find((r:any) => r.gps?.latitude && r.gps?.longitude);
      if (last) setLatestGps({ lat: last.gps.latitude, lon: last.gps.longitude, speedKph: last.gps?.speedKph });
    }
    loadHistory();
  }, [deviceId]);

  useEffect(() => {
    const socket = socketRef.current;
    if (!socket) return;
    const onTelemetry = (msg: any) => {
      if (msg.deviceId !== deviceId) return;
      if (msg.gps?.latitude && msg.gps?.longitude) {
        setLatestGps({ lat: msg.gps.latitude, lon: msg.gps.longitude, speedKph: msg.gps?.speedKph });
        setPath((prev: [number, number][]) => {
          const updated: [number, number][] = [...prev, [msg.gps.latitude, msg.gps.longitude]];
          return updated.slice(-500);
        });
      }
      if (msg.sensors) {
        if (typeof msg.sensors.temperatureC === 'number') setTemp(msg.sensors.temperatureC);
        if (typeof msg.sensors.humidityPct === 'number') setHumidity(msg.sensors.humidityPct);
      }
    };
    socket.on('telemetry', onTelemetry);
    return () => { socket.off('telemetry', onTelemetry) };
  }, [socketRef, deviceId]);

  const center = useMemo(() => {
    if (latestGps) return [latestGps.lat, latestGps.lon] as [number, number];
    return [37.7749, -122.4194] as [number, number];
  }, [latestGps]);

  async function sendCommand(command: string) {
    const payload = { deviceId, command, payload: {} };
    const resp = await fetch(`${API_BASE}/api/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-api-key': apiKey },
      body: JSON.stringify(payload)
    });
    const json = await resp.json();
    alert(json.ok ? 'Command sent' : 'Failed: ' + json.error);
  }

  async function requestInsight() {
    const resp = await fetch(`${API_BASE}/api/insights`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-api-key': apiKey },
      body: JSON.stringify({ deviceId, limit: 200 })
    });
    const json = await resp.json();
    setInsight(json.insight || json.error || 'No insight');
  }

  return (
    <div className="app">
      <header>
        <div style={{display:'flex', gap:12, alignItems:'center'}}>
          <strong>IoT Dashboard</strong>
          <div className="field">
            <label>Device</label>
            <input value={deviceId} onChange={e => setDeviceId(e.target.value)} />
          </div>
          <div className="field">
            <label>API Key</label>
            <input value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder="server API key" />
          </div>
        </div>
        <div className="row">
          <button className="btn" onClick={() => sendCommand('ping')}>Ping</button>
          <button className="btn" onClick={() => sendCommand('blink-led')}>Blink LED</button>
          <button className="btn" onClick={requestInsight}>AI Insight</button>
        </div>
      </header>
      <div className="content">
        <div className="card">
          <h3>Live Location</h3>
          <div className="map">
            <MapContainer center={center} zoom={13} style={{ height: '100%', width: '100%' }}>
              <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
              {latestGps && (
                <Marker position={[latestGps.lat, latestGps.lon]} icon={markerIcon}>
                  <Popup>
                    <div>
                      <div>Lat: {latestGps.lat.toFixed(6)}</div>
                      <div>Lon: {latestGps.lon.toFixed(6)}</div>
                      {latestGps.speedKph != null && <div>Speed: {latestGps.speedKph} kph</div>}
                    </div>
                  </Popup>
                </Marker>
              )}
              {path.length > 1 && (
                <Polyline positions={path} color="#2563eb" />
              )}
            </MapContainer>
          </div>
        </div>
        <div className="card">
          <h3>Sensors</h3>
          <div>Temperature: {temp != null ? `${temp.toFixed(1)} °C` : '—'}</div>
          <div>Humidity: {humidity != null ? `${humidity.toFixed(1)} %` : '—'}</div>
          <h3 style={{marginTop:16}}>AI Insight</h3>
          <pre style={{whiteSpace:'pre-wrap'}}>{insight || 'Click AI Insight to generate.'}</pre>
        </div>
      </div>
    </div>
  );
}
