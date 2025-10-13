from datetime import datetime, timezone
import time
from typing import Optional

from edge.gps_reader import GpsReader
from edge.telemetry import TelemetryClient, Event


def run_gps_publisher(
    telemetry_base_url: str,
    serial_port: str = "/dev/serial0",
    baudrate: int = 9600,
    period_seconds: float = 1.0,
) -> None:
    gps = GpsReader(serial_port, baudrate)
    gps.start()
    telem = TelemetryClient(telemetry_base_url)
    telem.start()

    try:
        while True:
            fix = gps.get_latest()
            if fix is not None:
                now = datetime.now(timezone.utc).isoformat()
                telem.publish(
                    Event(
                        timestamp_iso=now,
                        kind="gps",
                        payload={
                            "lat": fix.latitude,
                            "lon": fix.longitude,
                            "speed_kmh": fix.speed_kmh,
                            "course_deg": fix.course_deg,
                            "fix_quality": fix.fix_quality,
                            "num_satellites": fix.num_satellites,
                            "valid": fix.valid,
                        },
                    )
                )
            time.sleep(period_seconds)
    except KeyboardInterrupt:
        pass
    finally:
        telem.stop()
        gps.stop()
