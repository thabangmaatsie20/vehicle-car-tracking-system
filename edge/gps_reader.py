import threading
import time
from dataclasses import dataclass
from typing import Optional

try:
    import serial  # pyserial
    import pynmea2
except Exception:  # pragma: no cover - runtime on Pi
    serial = None
    pynmea2 = None


@dataclass
class GpsFix:
    timestamp_iso: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    speed_kmh: Optional[float]
    course_deg: Optional[float]
    fix_quality: Optional[int]
    num_satellites: Optional[int]
    valid: bool


class GpsReader:
    """
    Threaded GPS reader for NEO-6M via NMEA over UART.

    Usage:
        gps = GpsReader("/dev/serial0", 9600)
        gps.start()
        fix = gps.get_latest()
        gps.stop()
    """

    def __init__(self, port: str = "/dev/serial0", baudrate: int = 9600):
        self.port = port
        self.baudrate = baudrate
        self._serial = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest: Optional[GpsFix] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        if serial is None:
            raise RuntimeError("pyserial not available. Install with: pip install pyserial pynmea2")
        self._serial = serial.Serial(self.port, self.baudrate, timeout=1)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._thread = None
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

    def get_latest(self) -> Optional[GpsFix]:
        with self._lock:
            return self._latest

    def _run(self) -> None:  # pragma: no cover - hardware dependent
        last_timestamp_iso = None
        last_speed_kmh = None
        last_course_deg = None
        last_fix_quality = None
        last_num_satellites = None
        last_lat = None
        last_lon = None
        last_valid = False

        while not self._stop.is_set():
            try:
                raw_bytes = self._serial.readline()
                if not raw_bytes:
                    continue
                try:
                    raw = raw_bytes.decode(errors="ignore").strip()
                except Exception:
                    continue
                if not raw.startswith("$"):
                    continue
                if pynmea2 is None:
                    continue
                msg = pynmea2.parse(raw)
                st = getattr(msg, "sentence_type", "")
                if st == "RMC":
                    # Recommended Minimum: time, date, lat, lon, speed (knots), course, status
                    try:
                        if getattr(msg, "datestamp", None) and getattr(msg, "timestamp", None):
                            last_timestamp_iso = f"{msg.datestamp.isoformat()}T{msg.timestamp.isoformat()}"
                        elif getattr(msg, "timestamp", None):
                            last_timestamp_iso = msg.timestamp.isoformat()
                    except Exception:
                        pass
                    last_lat = getattr(msg, "latitude", last_lat)
                    last_lon = getattr(msg, "longitude", last_lon)
                    spd_knots = getattr(msg, "spd_over_grnd", None)
                    last_speed_kmh = float(spd_knots) * 1.852 if spd_knots not in (None, "") else None
                    crs = getattr(msg, "true_course", None)
                    last_course_deg = float(crs) if crs not in (None, "") else None
                    last_valid = (getattr(msg, "status", "V") == "A")
                elif st == "GGA":
                    # Fix data: quality, satellites, lat, lon
                    q = getattr(msg, "gps_qual", None)
                    last_fix_quality = int(q) if q not in (None, "") else None
                    s = getattr(msg, "num_sats", None)
                    last_num_satellites = int(s) if s not in (None, "") else None
                    last_lat = getattr(msg, "latitude", last_lat)
                    last_lon = getattr(msg, "longitude", last_lon)

                with self._lock:
                    self._latest = GpsFix(
                        timestamp_iso=last_timestamp_iso,
                        latitude=last_lat,
                        longitude=last_lon,
                        speed_kmh=last_speed_kmh,
                        course_deg=last_course_deg,
                        fix_quality=last_fix_quality,
                        num_satellites=last_num_satellites,
                        valid=bool(last_valid and last_lat and last_lon),
                    )
            except Exception:
                # Back off briefly on any error
                time.sleep(0.1)
