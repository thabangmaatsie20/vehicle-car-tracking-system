import json
import queue
import threading
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

import requests


@dataclass
class Event:
    timestamp_iso: str
    kind: str  # "gps" | "recognition"
    payload: Dict[str, Any]


class TelemetryClient:
    """
    Buffered, background HTTP telemetry client.
    Posts events to a dashboard HTTP endpoint.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._q: "queue.Queue[Event]" = queue.Queue(maxsize=1000)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def publish(self, event: Event) -> None:
        try:
            self._q.put_nowait(event)
        except queue.Full:
            # drop oldest by getting one, then put
            try:
                self._q.get_nowait()
            except Exception:
                pass
            try:
                self._q.put_nowait(event)
            except Exception:
                pass

    def _run(self) -> None:  # pragma: no cover - network dependent
        session = requests.Session()
        while not self._stop.is_set():
            try:
                event = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                url = f"{self.base_url}/api/events"
                session.post(url, json=asdict(event), timeout=3)
            except Exception:
                # brief backoff on failure
                time.sleep(0.2)
