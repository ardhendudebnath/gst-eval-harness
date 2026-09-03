"""The record of one model's run, and how it is stored.

One JSON file per run under `results/`, committed. Two fields exist because
model behaviour drifts under a fixed name and datasets drift under a fixed
path, and a leaderboard that cannot say *which* model and *which* dataset
produced a number is not reproducible:

  * `model_id` — the exact id string sent to the provider, plus the id the
    provider said served the request, which are not always the same.
  * `dataset_sha` — SHA-256 of the golden set as it stood. A result whose
    fingerprint no longer matches the current dataset is stale, and the
    leaderboard says so rather than quietly ranking it alongside fresh runs.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RESULTS = Path("results")
GOLDEN = Path("data/golden.jsonl")


def dataset_fingerprint(path: Path = GOLDEN) -> tuple[str, int]:
    """(sha256, row count) for the golden set. ('', 0) when it does not exist."""
    if not path.exists():
        return "", 0
    raw = path.read_bytes()
    rows = sum(1 for line in raw.splitlines() if line.strip())
    return hashlib.sha256(raw).hexdigest(), rows


@dataclass(slots=True)
class RunResult:
    run_id: str
    model_key: str
    model_id: str
    served_model_id: str
    provider: str
    tier: str
    prompt_version: str
    #: "shared" for the one-prompt-for-every-model pass the plan requires,
    #: "tuned" for the per-model pass reported alongside it.
    prompt_mode: str
    dataset_sha: str
    dataset_n: int
    started_at: str
    finished_at: str
    summary: dict[str, Any]
    cost: dict[str, Any]
    rows: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ""

    @property
    def run_date(self) -> str:
        return self.started_at[:10]

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, directory: Path = RESULTS) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.run_id}.json"
        path.write_text(
            json.dumps(self.to_json(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path

    @classmethod
    def load(cls, path: Path) -> "RunResult":
        data = json.loads(path.read_text(encoding="utf-8"))
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


def new_run_id(model_key: str, prompt_mode: str = "shared") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_{model_key}_{prompt_mode}"


#: Enough to tell a run result from any other JSON that lands in `results/`.
_RUN_MARKERS = ("run_id", "model_key", "summary")


def load_all(directory: Path = RESULTS) -> list[RunResult]:
    """Every run on disk, newest first.

    This is called straight after a paid run, so the two failure modes are
    deliberately not treated alike. A file that is not a run result at all —
    someone's scratch JSON, an editor's backup — is skipped with a note, rather
    than taking the leaderboard down over a file that was never ours. A file
    that *is* a run result but will not load still raises: that is a run
    someone paid for, and quietly dropping it would understate the record.
    """
    if not directory.exists():
        return []
    runs = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: {exc}") from exc

        if not isinstance(data, dict) or not any(m in data for m in _RUN_MARKERS):
            print(f"  {path.name}: not a run result, skipped", file=sys.stderr)
            continue

        known = {f for f in RunResult.__dataclass_fields__}  # type: ignore[attr-defined]
        try:
            runs.append(RunResult(**{k: v for k, v in data.items() if k in known}))
        except TypeError as exc:
            raise ValueError(f"{path}: {exc}") from exc
    return sorted(runs, key=lambda r: r.started_at, reverse=True)


def latest_per_model(runs: list[RunResult], prompt_mode: str = "shared") -> list[RunResult]:
    """The most recent run per model for one prompt mode.

    A model re-run after a fix should appear once, at its current score, not
    twice at two different scores.
    """
    seen: dict[str, RunResult] = {}
    for run in runs:  # already newest-first
        if run.prompt_mode != prompt_mode:
            continue
        seen.setdefault(run.model_key, run)
    return list(seen.values())
