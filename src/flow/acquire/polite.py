"""
A polite HTTP client for the data-acquisition agents.

Public data providers are called the way a careful person would call them:

  * one request at a time per host, spaced ``min_interval_seconds`` apart (or the
    provider's own figure, e.g. GDELT's one request every 5 s);
  * robots.txt is honoured; a disallowed path is never requested;
  * an honest User-Agent;
  * every response is cached on disk for the source's ``cache_hours``, so re-running
    an agent or a test does not call the provider again;
  * at most one retry, and only on 429 / 503, honouring ``Retry-After`` (max 60 s);
  * after ``circuit_failures`` consecutive failures a host is left alone for
    ``circuit_pause_minutes``.

``CAM_NETWORK_OFFLINE=1`` disables live calls (tests): a request then raises
``Offline`` and the agent falls back to documents.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib import robotparser
from urllib.parse import urlencode, urlsplit

import requests

log = logging.getLogger(__name__)


class NetworkError(RuntimeError):
    """The provider could not be reached or answered with an error."""


class Offline(NetworkError):
    """Live calls are disabled in this environment."""


class Disallowed(NetworkError):
    """robots.txt does not allow this path, or the host is paused after failures."""


@dataclass
class Response:
    url: str
    status: int
    content: bytes
    content_type: str
    from_cache: bool
    fetched_at: float

    def json(self):
        return json.loads(self.content.decode("utf-8"))

    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


class PoliteClient:
    def __init__(self, cache_dir: Path, *, user_agent: str, min_interval: float = 3.0, timeout: float = 25.0,
                 respect_robots: bool = True, max_retries: int = 1, circuit_failures: int = 2,
                 circuit_pause_minutes: float = 15, max_response_mb: float = 40,
                 host_intervals: Optional[dict] = None, session: Optional[requests.Session] = None):
        self.cache_dir = Path(cache_dir)
        self.user_agent = user_agent
        self.min_interval = float(min_interval)
        self.timeout = float(timeout)
        self.respect_robots = respect_robots
        self.max_retries = int(max_retries)
        self.circuit_failures = int(circuit_failures)
        self.circuit_pause = float(circuit_pause_minutes) * 60
        self.max_bytes = int(float(max_response_mb) * 1024 * 1024)
        self.host_intervals = {k: float(v) for k, v in (host_intervals or {}).items()}
        self.session = session or requests.Session()
        self._guard = threading.Lock()
        self._host_locks: dict[str, threading.Lock] = {}
        self._last_call: dict[str, float] = {}
        self._failures: dict[str, int] = {}
        self._paused_until: dict[str, float] = {}
        self._robots: dict[str, Optional[robotparser.RobotFileParser]] = {}
        self.calls: list[dict] = []                 # live calls made (for the audit trail)

    @classmethod
    def from_config(cls, cfg: dict, cache_dir: Path) -> "PoliteClient":
        n = cfg or {}
        return cls(cache_dir, user_agent=n.get("user_agent") or "CorporateCreditOrigination-UAT/1.0",
                   min_interval=n.get("min_interval_seconds", 3), timeout=n.get("timeout_seconds", 25),
                   respect_robots=n.get("respect_robots", True), max_retries=n.get("max_retries", 1),
                   circuit_failures=n.get("circuit_failures", 2),
                   circuit_pause_minutes=n.get("circuit_pause_minutes", 15),
                   max_response_mb=n.get("max_response_mb", 40), host_intervals=n.get("hosts") or {})

    @staticmethod
    def offline() -> bool:
        return os.getenv("CAM_NETWORK_OFFLINE", "").strip().lower() in ("1", "true", "yes")

    # ── public ───────────────────────────────────────────────────────────────

    def get(self, url: str, *, params: Optional[dict] = None, cache_hours: float = 24,
            accept: str = "application/json") -> Response:
        full = url + (("&" if "?" in url else "?") + urlencode(params, doseq=True) if params else "")
        cached = self._cached(full, cache_hours)
        if cached:
            return cached
        if self.offline():
            raise Offline("Live API calls are disabled in this environment (CAM_NETWORK_OFFLINE)")
        host = urlsplit(full).netloc.lower()
        if time.time() < self._paused_until.get(host, 0):
            raise Disallowed(f"{host} is paused after repeated failures; try again later")
        if self.respect_robots and not self._allowed(full):
            raise Disallowed(f"robots.txt of {host} does not allow this request")
        with self._host_lock(host):
            resp = self._fetch(full, host, accept)
        self._store(full, resp)
        return resp

    # ── internals ────────────────────────────────────────────────────────────

    def _host_lock(self, host: str) -> threading.Lock:
        with self._guard:
            return self._host_locks.setdefault(host, threading.Lock())

    def _space(self, host: str) -> None:
        gap = self.host_intervals.get(host, self.min_interval)
        wait = self._last_call.get(host, 0) + gap - time.time()
        if wait > 0:
            time.sleep(wait)

    def _fetch(self, url: str, host: str, accept: str) -> Response:
        attempt = 0
        while True:
            self._space(host)
            started = time.time()
            try:
                r = self.session.get(url, timeout=self.timeout, stream=True,
                                     headers={"User-Agent": self.user_agent, "Accept": accept})
                content = self._read_capped(r)
            except requests.RequestException as e:
                self._last_call[host] = time.time()
                self._fail(host)
                self._record(url, None, 0, started, error=str(e))
                raise NetworkError(f"{host} could not be reached: {type(e).__name__}") from e
            self._last_call[host] = time.time()
            self._record(url, r.status_code, len(content), started)
            if r.status_code in (429, 503) and attempt < self.max_retries:
                attempt += 1
                retry_after = r.headers.get("Retry-After", "")
                delay = min(60.0, float(retry_after)) if retry_after.isdigit() else 10.0
                log.info("%s answered %s; waiting %.0fs before one retry", host, r.status_code, delay)
                time.sleep(delay)
                continue
            if r.status_code >= 400:
                self._fail(host)
                raise NetworkError(f"{host} answered HTTP {r.status_code}")
            self._failures[host] = 0
            return Response(url=url, status=r.status_code, content=content,
                            content_type=r.headers.get("Content-Type", ""), from_cache=False,
                            fetched_at=time.time())

    def _read_capped(self, r) -> bytes:
        chunks, size = [], 0
        for chunk in r.iter_content(chunk_size=65536):
            size += len(chunk)
            if size > self.max_bytes:
                r.close()
                raise requests.RequestException(f"response larger than {self.max_bytes // (1024 * 1024)} MB")
            chunks.append(chunk)
        return b"".join(chunks)

    def _fail(self, host: str) -> None:
        n = self._failures.get(host, 0) + 1
        self._failures[host] = n
        if n >= self.circuit_failures:
            self._paused_until[host] = time.time() + self.circuit_pause
            log.warning("%s paused for %.0f min after %d failures", host, self.circuit_pause / 60, n)

    def _record(self, url: str, status: Optional[int], size: int, started: float, error: str = "") -> None:
        entry = {"url": url, "status": status, "bytes": size, "ms": round((time.time() - started) * 1000),
                 "at": time.strftime("%Y-%m-%dT%H:%M:%S"), **({"error": error} if error else {})}
        with self._guard:
            self.calls.append(entry)
            del self.calls[:-200]
        log.info("GET %s -> %s (%d bytes, %d ms)", url, status, size, entry["ms"])

    def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        with self._guard:
            known = base in self._robots
            rp = self._robots.get(base)
        if not known:
            rp = None
            try:
                with self._host_lock(parts.netloc.lower()):
                    self._space(parts.netloc.lower())
                    r = self.session.get(base + "/robots.txt", timeout=self.timeout,
                                         headers={"User-Agent": self.user_agent})
                    self._last_call[parts.netloc.lower()] = time.time()
                if r.status_code == 200 and "text" in r.headers.get("Content-Type", "text/plain"):
                    rp = robotparser.RobotFileParser()
                    rp.parse(r.text.splitlines())
            except requests.RequestException:
                rp = None                       # no robots.txt reachable: nothing disallowed
            with self._guard:
                self._robots[base] = rp
        return rp is None or rp.can_fetch(self.user_agent, url)

    def _key(self, url: str) -> Path:
        return self.cache_dir / hashlib.sha256(url.encode("utf-8")).hexdigest()[:40]

    def _cached(self, url: str, cache_hours: float) -> Optional[Response]:
        key = self._key(url)
        meta, body = key.with_suffix(".json"), key.with_suffix(".bin")
        if not (meta.exists() and body.exists()):
            return None
        try:
            m = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if time.time() - m.get("fetched_at", 0) > cache_hours * 3600:
            return None
        return Response(url=url, status=m.get("status", 200), content=body.read_bytes(),
                        content_type=m.get("content_type", ""), from_cache=True, fetched_at=m["fetched_at"])

    def _store(self, url: str, resp: Response) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            key = self._key(url)
            key.with_suffix(".bin").write_bytes(resp.content)
            key.with_suffix(".json").write_text(json.dumps(
                {"url": url, "status": resp.status, "content_type": resp.content_type,
                 "fetched_at": resp.fetched_at}), encoding="utf-8")
        except OSError:
            log.warning("Could not cache %s", url, exc_info=True)
