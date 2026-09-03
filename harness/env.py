"""Read `.env` into the process environment.

The repo has shipped a `.env.example` and a README line telling you to copy it
to `.env` since week 1, and nothing ever read the result. Following that
instruction produced a file the harness ignored, and then a runner reporting
`NVIDIA_API_KEY is not set` while the key sat in `.env` — a confusing way to
lose an afternoon, and entirely our fault for documenting a loader that did not
exist.

Stdlib only. python-dotenv would be a dependency to parse `KEY=value`, and the
rest of this package deliberately imports nothing.

A real environment variable always wins. Someone who exports a key for one
command means it for that command, and a stale `.env` silently overriding it is
the failure mode that makes dotenv loaders untrustworthy.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ENV = Path(".env")


def parse(text: str) -> dict[str, str]:
    """Parse dotenv text. Blank values are dropped, not stored as empty.

    `.env.example` ships every key present and empty, so a copied-but-unfilled
    file would otherwise set `ANTHROPIC_API_KEY=""` — which reads as "set" to
    anything checking membership rather than truth.
    """
    found: dict[str, str] = {}
    # A leading BOM is normal for a file written by a Windows editor, and would
    # otherwise become part of the first key's name.
    for raw in text.lstrip("﻿").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        # `export FOO=bar` is a common shape in a file people also source.
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and value:
            found[key] = value
    return found


def load(path: Path | None = None, *, override: bool = False) -> list[str]:
    """Load `path` into os.environ. Returns the names set, never the values."""
    path = DEFAULT_ENV if path is None else path
    if not path.is_file():
        return []

    applied = []
    for key, value in parse(path.read_text(encoding="utf-8")).items():
        if override or not os.environ.get(key):
            os.environ[key] = value
            applied.append(key)
    return applied
