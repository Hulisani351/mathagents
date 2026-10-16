"""Cloud-safe solver boundary. No silent fallback and no secrets in result exports."""
from __future__ import annotations

import json
import hashlib
import math
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from engine import single_agent, multi_agent


class SolverError(Exception):
    """A safe, actionable message for the user."""


def retry_delay(value: str | None, attempt: int) -> float:
    delay = min(60, 5 * 2 ** attempt)
    if value:
        try:
            seconds = float(value)
            if math.isfinite(seconds):
                delay = max(delay, seconds)
        except ValueError:
            try:
                date = parsedate_to_datetime(value)
                delay = max(delay, (date - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError):
                pass
    return max(0, delay)


class RequestGate:
    """One shared server gate and provider cooldown, with a daily request ceiling."""
    def __init__(self, daily_limit: int = 300):
        self.lock = threading.Lock()
        # The provider may allow only one in-flight request. Keep blind solver
        # contexts independent, but serialize outbound calls across app sessions.
        self.semaphore = threading.BoundedSemaphore(1)
        self.until = 0.0
        self.next_request = 0.0
        self.date = datetime.now(timezone.utc).date()
        self.used = 0
        self.daily_limit = daily_limit

    def remaining(self):
        with self.lock:
            return max(0, math.ceil(self.until - time.monotonic()))

    def reserve(self):
        deadline = time.monotonic() + 60
        while True:
            with self.lock:
                today = datetime.now(timezone.utc).date()
                if today != self.date:
                    self.date, self.used = today, 0
                if self.used >= self.daily_limit:
                    raise SolverError("This server has reached its daily request allowance. Use Presentation (saved), or return tomorrow.")
                now = time.monotonic()
                remaining = max(self.until, self.next_request) - now
                if remaining <= 0:
                    self.used += 1
                    self.next_request = now + 2
                    return
                if now + remaining > deadline:
                    raise SolverError(f"The provider is cooling down. Please retry in {math.ceil(remaining)} seconds, or open Presentation (saved).")
            time.sleep(remaining)

    def cooldown(self, seconds):
        with self.lock:
            self.until = max(self.until, time.monotonic() + seconds)


@dataclass
class CloudClient:
    api_key: str = field(repr=False)
    model: str = "glm-4.7-flash"
    provider_name: str = "z-ai-glm"
    gate: RequestGate = field(default_factory=RequestGate, repr=False)
    response_cache: dict = field(default_factory=dict, repr=False)
    cache_lock: object = field(default_factory=threading.Lock, repr=False)
    reused_stages: list = field(default_factory=list, repr=False)

    def generate(self, role, prompt, context=None):
        payload = {"model": self.model, "temperature": 0, "max_tokens": 2048,
                   "thinking": {"type": "disabled"},
                   "messages": [{"role": "user", "content": prompt}]}
        # This cache belongs to ONE browser session, never st.cache_data/resource.
        # Include account + full request, not just question or role, in the key.
        key = hashlib.sha256((self.api_key + json.dumps(payload, sort_keys=True)).encode()).hexdigest()
        with self.cache_lock:
            cached = self.response_cache.get(key)
            if cached:
                self.reused_stages.append({"role": role, "generated_at": cached["generated_at"]})
                return cached["text"]
        request = urllib.request.Request(
            "https://api.z.ai/api/paas/v4/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"},
            method="POST")
        if not self.gate.semaphore.acquire(timeout=240):
            raise SolverError("The live solver queue is busy. Your question is preserved. Use Presentation (saved), or try again later.")
        try:
            for attempt in range(3):
                self.gate.reserve()
                try:
                    with urllib.request.urlopen(request, timeout=60) as response:
                        data = json.loads(response.read(2_000_000))
                    choice = data["choices"][0]
                    if choice.get("finish_reason") == "length":
                        raise SolverError("The model reached its answer length limit. Try a more focused question.")
                    text = choice["message"]["content"]
                    if not isinstance(text, str) or not text.strip():
                        raise SolverError("The model returned an empty answer. Please try again.")
                    with self.cache_lock:
                        self.response_cache[key] = {"text": text.strip(), "generated_at": datetime.now(timezone.utc).isoformat()}
                        while len(self.response_cache) > 60:
                            del self.response_cache[next(iter(self.response_cache))]
                    return text.strip()
                except urllib.error.HTTPError as exc:
                    # Never surface raw error bodies: they may contain private data.
                    try:
                        code = str(json.loads(exc.read(16_384)).get("error", {}).get("code", ""))
                    except (ValueError, TypeError, AttributeError):
                        code = ""
                    if exc.code in (401, 403):
                        raise SolverError("The provider rejected the API credential. The app owner must check the server secret.") from None
                    if exc.code == 402 or code == "1113":
                        raise SolverError("The provider account has no available credit/resource package. The owner must check the account; automatic retries stopped. Presentation (saved) remains available.") from None
                    if code in {"1308", "1309", "1310", "1311", "1313", "1314", "1315", "1316", "1317", "1318", "1319", "1320", "1321"}:
                        raise SolverError("The provider reports an account usage or plan restriction (code " + code + "). Automatic retries stopped. Check the provider console or use Presentation (saved).") from None
                    if exc.code == 429 or 500 <= exc.code <= 504:
                        delay = retry_delay(exc.headers.get("Retry-After"), attempt)
                        if exc.code == 429:
                            delay = max(delay, 15 * 2 ** attempt)
                        self.gate.cooldown(delay)
                        if attempt < 2 and delay <= 60:
                            continue
                        raise SolverError(f"The provider is temporarily unavailable after bounded retries. Wait {math.ceil(delay)} seconds, then retry this question; successful stages are retained in this session. Presentation (saved) needs no provider calls.") from None
                    raise SolverError(f"The provider rejected this request (HTTP {exc.code}). Please contact the app owner.") from None
                except (urllib.error.URLError, TimeoutError):
                    if attempt == 2:
                        raise SolverError("The provider connection timed out. Your question remains in the editor.") from None
                    self.gate.cooldown(5 * (attempt + 1))
                except (KeyError, IndexError, TypeError, ValueError):
                    raise SolverError("The provider returned an unexpected response. Please try again later.") from None
        finally:
            self.gate.semaphore.release()


def solve_question(problem: str, mode: str, client) -> dict:
    problem = problem.strip()
    if not problem:
        raise SolverError("Enter a mathematics question first.")
    if len(problem) > 4000:
        raise SolverError("Please keep the question below 4,000 characters.")
    if mode not in ("single", "multi"):
        raise SolverError("Choose Single agent or Multi-agent team.")
    start = time.perf_counter()
    pipeline = single_agent if mode == "single" else multi_agent
    result = pipeline.solve(problem, client).to_dict()
    result.update({"elapsed_seconds": round(time.perf_counter() - start, 2),
                   "model": client.model, "provider": client.provider_name,
                   "architecture_version": pipeline.ARCHITECTURE_VERSION,
                   "created_at": datetime.now(timezone.utc).isoformat(),
                   "notice": "AI-generated solution. Agreement is not proof of correctness."})
    reused = list(getattr(client, "reused_stages", []))
    result.update({"reused_stages": reused,
                   "execution_source": "session_cache_or_resume" if reused else "live_provider",
                   "runtime_scope": "This attempt, including queue/cooldown; excludes original generation time of reused stages."})
    return result
