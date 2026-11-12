"""Optional application cache with Redis or in-memory backends."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

try:
    import redis
except ImportError:  # pragma: no cover - optional dependency
    redis = None


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class MemoryCacheBackend:
    def __init__(self):
        self._values: dict[str, tuple[str, float | None]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            item = self._values.get(key)
            if not item:
                return None
            value, expires_at = item
            if expires_at is not None and expires_at <= time.time():
                self._values.pop(key, None)
                return None
            return value

    def setex(self, key: str, ttl_seconds: int, value: str):
        expires_at = time.time() + ttl_seconds if ttl_seconds > 0 else None
        with self._lock:
            self._values[key] = (value, expires_at)

    def set(self, key: str, value: str):
        with self._lock:
            self._values[key] = (value, None)

    def incr(self, key: str) -> int:
        """Increment a counter, mirroring Redis INCR semantics.

        The counter is stored in the same keyspace ``get`` reads from, so
        version lookups (which go through ``get``) observe increments.
        """
        with self._lock:
            item = self._values.get(key)
            current = 0
            if item is not None:
                try:
                    current = int(item[0])
                except (TypeError, ValueError):
                    current = 0
            next_value = current + 1
            self._values[key] = (str(next_value), None)
            return next_value


class CacheManager:
    def __init__(self):
        self._backend = None
        self._backend_name = "disabled"
        self._enabled = _env_flag("CACHE_ENABLED", True)
        self._default_backend = os.getenv("CACHE_BACKEND", "").strip().lower()
        self._redis_url = os.getenv("REDIS_URL", "").strip()

    @property
    def enabled(self) -> bool:
        return self._enabled and self._backend is not None

    @property
    def backend_name(self) -> str:
        return self._backend_name

    def initialize(self):
        if not self._enabled:
            self._backend = None
            self._backend_name = "disabled"
            return

        preferred = self._default_backend
        if not preferred:
            preferred = "redis" if self._redis_url else "memory"

        if preferred == "redis":
            self._initialize_redis()
        elif preferred == "memory":
            self._backend = MemoryCacheBackend()
            self._backend_name = "memory"
            logger.info("Cache enabled with in-memory backend")
        else:
            logger.warning("Unknown CACHE_BACKEND=%s; cache disabled", preferred)
            self._backend = None
            self._backend_name = "disabled"

    def _initialize_redis(self):
        if not self._redis_url:
            logger.warning("CACHE_BACKEND=redis but REDIS_URL is not configured; falling back to memory cache")
            self._backend = MemoryCacheBackend()
            self._backend_name = "memory"
            return

        if redis is None:
            logger.warning("Redis package not installed; falling back to memory cache")
            self._backend = MemoryCacheBackend()
            self._backend_name = "memory"
            return

        try:
            client = redis.Redis.from_url(self._redis_url, decode_responses=True)
            client.ping()
        except Exception as exc:  # pragma: no cover - depends on environment
            logger.warning("Redis cache unavailable (%s); falling back to memory cache", exc)
            self._backend = MemoryCacheBackend()
            self._backend_name = "memory"
            return

        self._backend = client
        self._backend_name = "redis"
        logger.info("Cache enabled with Redis backend")

    def build_key(self, namespace: str, *parts: Any) -> str:
        version = self._get_namespace_version(namespace)
        key_parts = ["cache", namespace, f"v{version}"]
        for part in parts:
            if part is None:
                continue
            key_parts.append(str(part))
        return ":".join(key_parts)

    def bump(self, namespace: str):
        if not self.enabled:
            return
        try:
            self._backend.incr(self._version_key(namespace))
        except Exception as exc:  # pragma: no cover - depends on backend
            logger.warning("Cache namespace bump failed for %s: %s", namespace, exc)

    def get_json(self, key: str):
        if not self.enabled:
            return None
        try:
            payload = self._backend.get(key)
        except Exception as exc:  # pragma: no cover - depends on backend
            logger.warning("Cache read failed for %s: %s", key, exc)
            return None

        if payload is None:
            return None

        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None

    def set_json(self, key: str, value: Any, ttl_seconds: int | None = None):
        if not self.enabled:
            return

        serialized = json.dumps(value, separators=(",", ":"), ensure_ascii=True)
        try:
            if ttl_seconds and ttl_seconds > 0:
                self._backend.setex(key, ttl_seconds, serialized)
            else:
                self._backend.set(key, serialized)
        except Exception as exc:  # pragma: no cover - depends on backend
            logger.warning("Cache write failed for %s: %s", key, exc)

    def ttl(self, name: str, default_seconds: int) -> int:
        raw_value = os.getenv(name)
        if raw_value is None:
            return default_seconds
        try:
            return max(0, int(raw_value))
        except ValueError:
            logger.warning("Invalid cache TTL for %s=%s; using default %s", name, raw_value, default_seconds)
            return default_seconds

    def _get_namespace_version(self, namespace: str) -> int:
        if not self.enabled:
            return 0
        try:
            value = self._backend.get(self._version_key(namespace))
        except Exception as exc:  # pragma: no cover - depends on backend
            logger.warning("Cache version read failed for %s: %s", namespace, exc)
            return 0
        if value is None:
            return 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _version_key(namespace: str) -> str:
        return f"cache-version:{namespace}"


cache = CacheManager()
