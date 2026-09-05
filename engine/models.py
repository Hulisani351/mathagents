from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TraceEvent:
    timestamp: str
    stage: str
    payload: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PipelineResult:
    mode: str
    problem: str
    final_answer: str
    trace: List[TraceEvent]
    verdict: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "problem": self.problem,
            "final_answer": self.final_answer,
            "verdict": self.verdict,
            "trace": [event.to_dict() for event in self.trace],
        }