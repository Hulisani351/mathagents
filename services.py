"""Cloud-safe solver boundary. No silent fallback and no secrets in result exports."""
from __future__ import annotations

import json
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
            delay = max(delay, float(value))
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
        self.semaphore = threading.BoundedSemaphore(2)
        self.until = 0.0
        self.date = datetime.now(timezone.utc).date()
        self.used = 0
        self.daily_limit = daily_limit

    def reserve(self):
        with self.lock:
            today = datetime.now(timezone.utc).date()
            if today != self.date:
                self.date, self.used = today, 0
            if self.used >= self.daily_limit:
                raise SolverError("This server has reached its daily request allowance. Please return tomorrow.")
            remaining = self.until - time.monotonic()
            if remaining > 30:
                raise SolverError(f"The provider is cooling down. Please retry in {int(remaining) + 1} seconds.")
            self.used += 1
        if remaining > 0:
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

    def generate(self, role, prompt, context=None):
        payload = {"model": self.model, "temperature": 0, "max_tokens": 2048,
                   "thinking": {"type": "disabled"},
                   "messages": [{"role": "user", "content": prompt}]}
        request = urllib.request.Request(
            "https://api.z.ai/api/paas/v4/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"},
            method="POST")
        if not self.gate.semaphore.acquire(timeout=2):
            raise SolverError("Both solver slots are busy. Please try again shortly.")
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
                    return text.strip()
                except urllib.error.HTTPError as exc:
                    if exc.code in (401, 403):
                        raise SolverError("The provider rejected the API credential. The app owner must check the server secret.") from None
                    if exc.code == 402:
                        raise SolverError("The provider account needs credit. No answer has been generated.") from None
                    if exc.code == 429 or 500 <= exc.code <= 504:
                        delay = retry_delay(exc.headers.get("Retry-After"), attempt)
                        self.gate.cooldown(delay)
                        if attempt < 2 and delay <= 30:
                            continue
                        raise SolverError(f"The provider is temporarily unavailable. Please retry in {int(delay) + 1} seconds.") from None
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
    return result
