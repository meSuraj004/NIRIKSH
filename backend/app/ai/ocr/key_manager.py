"""
=============================================================================
Groq API Key Manager & Intelligent Rotator
=============================================================================
Module: ocr.key_manager
Purpose:
  Manages a thread-safe pool of Groq API keys with round-robin request distribution,
  rate-limit (HTTP 429) cooldowns, automatic key rotation, and health telemetry.

Key Architectural Features:
  1. Multi-Key Key Pool:
     - Aggregates keys from parameter arguments or the GROQ_API_KEYS environment variable.
  2. Intelligent Rate-Limit Cooldown:
     - On encountering HTTP 429 / RateLimitError, the failed key is placed into a
       temporary cooldown (default 60 seconds).
     - The request is immediately retried on the next available active key without
       failing the user request.
  3. Thread-Safe Concurrency:
     - Protected with threading.Lock to support parallel multi-threaded pipeline executions.
=============================================================================
"""

import time
import threading
from typing import List, Optional, Tuple, Any, Callable
from groq import Groq, RateLimitError, APIError

from app.config import settings


class GroqKeyManager:
    """
    Thread-safe Groq API Key Pool & Rotation Manager.
    """

    def __init__(self, keys: Optional[List[str]] = None):
        """
        Initializes key pool, client cache, and telemetry metrics.

        Args:
            keys: Optional list of explicit API key strings (defaults to GROQ_API_KEYS env).
        """
        self.lock = threading.Lock()
        
        self.keys: List[str] = []
        self._clients: dict = {}
        self._cooldowns: dict = {}   # key -> cooldown_expiry_timestamp
        self._current_index = 0
        self._stats: dict = {}       # key -> {"calls": 0, "rate_limits": 0, "errors": 0}

        # Load keys from file, environment, or defaults
        self._load_keys(keys)
        print(f"[GroqKeyManager] Initialized with {len(self.keys)} active API keys.")

    def _load_keys(self, provided_keys: Optional[List[str]] = None):
        """Discovers and parses valid Groq API keys matching pattern 'gsk_...'."""
        loaded = []

        if provided_keys:
            loaded.extend(provided_keys)

        # Keys come exclusively from the GROQ_API_KEYS environment variable.
        # If none are configured, the pool stays empty and API calls fail fast.
        loaded.extend(settings.groq_api_keys)

        # Deduplicate while preserving order
        seen = set()
        for k in loaded:
            k_clean = k.strip()
            if k_clean and k_clean not in seen:
                seen.add(k_clean)
                self.keys.append(k_clean)
                self._stats[k_clean] = {"calls": 0, "rate_limits": 0, "errors": 0}

    def _get_client_for_key(self, api_key: str) -> Groq:
        """Retrieves or creates a cached Groq client instance for the specified API key."""
        if api_key not in self._clients:
            self._clients[api_key] = Groq(api_key=api_key)
        return self._clients[api_key]

    def get_available_key(self) -> Tuple[str, Groq]:
        """
        Returns the next available (non-cooldown) API key and Groq client instance.

        Returns:
            Tuple[str, Groq]: (active_api_key_str, groq_client_instance)

        Raises:
            RuntimeError: If all API keys in the pool are currently in cooldown.
        """
        with self.lock:
            if not self.keys:
                raise RuntimeError("No Groq API keys configured in pool.")

            now = time.time()
            total_keys = len(self.keys)

            # Round-robin scan for next non-cooldown key
            for attempt in range(total_keys):
                idx = (self._current_index + attempt) % total_keys
                cand_key = self.keys[idx]
                cooldown_until = self._cooldowns.get(cand_key, 0)

                if now >= cooldown_until:
                    # Key is active and ready
                    self._current_index = (idx + 1) % total_keys
                    client = self._get_client_for_key(cand_key)
                    self._stats[cand_key]["calls"] += 1
                    return cand_key, client

            # If all keys are cooling down, select the one expiring soonest
            soonest_key = min(self.keys, key=lambda k: self._cooldowns.get(k, 0))
            wait_time = max(1.0, round(self._cooldowns.get(soonest_key, now) - now, 1))
            print(f"[GroqKeyManager] All keys rate-limited. Waiting {wait_time}s on soonest key...")
            time.sleep(min(wait_time, 5.0))
            
            client = self._get_client_for_key(soonest_key)
            self._stats[soonest_key]["calls"] += 1
            return soonest_key, client

    def report_rate_limit(self, key: str, cooldown_seconds: float = 60.0):
        """
        Marks an API key as rate-limited and applies a cooldown period.

        Args:
            key: The API key that received HTTP 429.
            cooldown_seconds: Duration in seconds to cool down the key.
        """
        with self.lock:
            self._cooldowns[key] = time.time() + cooldown_seconds
            if key in self._stats:
                self._stats[key]["rate_limits"] += 1
            masked = key[:8] + "..." + key[-4:]
            print(f"[GroqKeyManager] ⚠️ Key {masked} rate-limited. Cooldown for {cooldown_seconds}s.")

    def report_error(self, key: str):
        """Records an API error on the specified key for health tracking."""
        with self.lock:
            if key in self._stats:
                self._stats[key]["errors"] += 1

    def execute_with_retry(
        self,
        api_callable: Callable[[Groq], Any],
        max_attempts: Optional[int] = None
    ) -> Any:
        """
        Executes a Groq API request with automatic rate-limit detection and key rotation.

        Args:
            api_callable: Function taking a Groq client argument and executing the call.
            max_attempts: Maximum rotation attempts (defaults to 2x number of keys in pool).

        Returns:
            Any: Response object from the API callable.
        """
        attempts = 0
        limit = max_attempts or (len(self.keys) * 2 + 1)
        last_exception = None

        while attempts < limit:
            attempts += 1
            key, client = self.get_available_key()

            try:
                result = api_callable(client)
                return result

            except RateLimitError as rle:
                last_exception = rle
                self.report_rate_limit(key, cooldown_seconds=60.0)
                time.sleep(0.5)
                continue

            except APIError as ae:
                last_exception = ae
                err_msg = str(ae).lower()
                if "rate limit" in err_msg or "429" in err_msg or "tpm" in err_msg or "rpm" in err_msg:
                    self.report_rate_limit(key, cooldown_seconds=60.0)
                    time.sleep(0.5)
                else:
                    self.report_error(key)
                    masked = key[:8] + "..." + key[-4:]
                    print(f"[GroqKeyManager] API error on key {masked}: {ae}. Retrying next key ({attempts}/{limit})...")
                    time.sleep(0.8)
                continue

            except Exception as e:
                last_exception = e
                self.report_error(key)
                masked = key[:8] + "..." + key[-4:]
                print(f"[GroqKeyManager] Request exception on key {masked}: {e}. Retrying next key ({attempts}/{limit})...")
                time.sleep(0.8)
                continue

        raise RuntimeError(f"Groq API call failed after {attempts} attempts across key pool. Last error: {last_exception}")

    def get_status_summary(self) -> List[dict]:
        """Returns diagnostic status of all keys in pool."""
        with self.lock:
            now = time.time()
            summary = []
            for i, k in enumerate(self.keys):
                cooldown_left = max(0.0, self._cooldowns.get(k, 0) - now)
                key_prefix = k[:12] if len(k) >= 12 else k
                stats = self._stats.get(k, {})
                summary.append({
                    "index": i + 1,
                    "key_prefix": key_prefix,
                    "key_masked": f"{k[:8]}...{k[-4:]}",
                    "status": "COOLDOWN" if cooldown_left > 0 else "ACTIVE",
                    "cooldown_remaining_sec": round(cooldown_left, 1),
                    "cooldown_left_sec": round(cooldown_left, 1),
                    "total_calls": stats.get("calls", 0),
                    "stats": stats
                })
            return summary


# Global singleton instance for shared key rotation across all OCR & LLM components
key_manager = GroqKeyManager()
