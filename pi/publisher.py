#!/usr/bin/env python3
import json
import os
import time
import threading
from typing import Optional

import paho.mqtt.client as mqtt
import serial
import pynmea2

MQTT_URL = os.getenv('MQTT_URL', 'mqtt://localhost:1883')
MQTT_HOST = os.getenv('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.getenv('MQTT_PORT', '1883'))
MQTT_USERNAME = os.getenv('MQTT_USERNAME', '')
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD', '')
DEVICE_ID = os.getenv('DEVICE_ID', 'pi-1')
TELEMETRY_TOPIC = os.getenv('TELEMETRY_TOPIC', f'iot/{DEVICE_ID}/telemetry')
COMMAND_TOPIC = os.getenv('COMMAND_TOPIC', f'iot/{DEVICE_ID}/commands')

# Neo-6M default serial device on many Pi setups (enable serial):
GPS_SERIAL = os.getenv('GPS_SERIAL', '/dev/ttyAMA0')  # or '/dev/serial0'
GPS_BAUD = int(os.getenv('GPS_BAUD', '9600'))

# Optional additional sensors would be read here (I2C, SPI, etc.)

class GpsReader(threading.Thread):
    def __init__(self, port: str, baud: int):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self._last_fix = None
        self._stop = threading.Event()

    def run(self):
        try:
            with serial.Serial(self.port, self.baud, timeout=1) as ser:
                while not self._stop.is_set():
                    line = ser.readline().decode('ascii', errors='ignore').strip()
                    if line.startswith('$GPRMC') or line.startswith('$GNRMC'):
                        try:
                            msg = pynmea2.parse(line)
                            if msg.status == 'A':  # active fix
                                lat = float(msg.latitude)
                                lon = float(msg.longitude)
                                spd_knots = float(msg.spd_over_grnd or 0.0)
                                spd_kph = spd_knots * 1.852
                                self._last_fix = {
                                    'latitude': lat,
                                    'longitude': lon,
                                    'speedKph': round(spd_kph, 2)
                                }
                        except Exception:
                            pass
        except serial.SerialException:
            # No serial available; keep thread idle
            while not self._stop.is_set():
                time.sleep(1)

    def get_last_fix(self) -> Optional[dict]:
        return self._last_fix

    def stop(self):
        self._stop.set()


def on_connect(client, userdata, flags, rc, properties=None):
    print('[MQTT] Connected', rc)
    client.subscribe(COMMAND_TOPIC)


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        command = payload.get('command')
        if command == 'ping':
            print('[CMD] ping received')
        elif command == 'blink-led':
            print('[CMD] blink-led received (implement GPIO toggle here)')
        else:
            print('[CMD] unknown:', command)
    except Exception as e:
        print('[CMD] error:', e)


def main():
    client = mqtt.Client(client_id=f'{DEVICE_ID}-pub', protocol=mqtt.MQTTv5)
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)

    gps = GpsReader(GPS_SERIAL, GPS_BAUD)
    gps.start()

    try:
        while True:
            fix = gps.get_last_fix()
            sensors = {
                # Add real sensor reads here
                'temperatureC': None,
                'humidityPct': None
            }
            msg = {
                'deviceId': DEVICE_ID,
                'type': 'telemetry',
                'gps': fix,
                'sensors': sensors,
                'ts': int(time.time() * 1000)
            }
            client.publish(TELEMETRY_TOPIC, json.dumps(msg))
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    finally:
        gps.stop()
        client.disconnect()


if __name__ == '__main__':
    main()
