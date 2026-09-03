"""Look a tariff heading up in the archived Gazette notifications.

This is a document lookup, not a judgement. It reads the hash-pinned copies in
`data/reference/primary/` and reports which Schedule a heading appears in, so a
rate can be cited rather than recalled — which matters, because a model's
recollection of Indian GST rates is exactly the pre-2025 table this benchmark
exists to catch out.

**It refuses to guess.** A heading that appears in more than one Schedule is
reported as ambiguous with all its entries, never resolved. Those are the
conditional cases — 7418 splits on whether an article is a household article of
copper, 8711 on engine capacity, 2202 on added sugar — and picking one is a
judgement about the goods, which is the annotator's job.

    from harness.collect.schedule_lookup import lookup
    lookup("9608")   -> Match(schedule="II", slab="18", ...)
    lookup("7418")   -> Match(ambiguous=True, entries=[...])
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

PRIMARY = Path("data/reference/primary")
RATED = PRIMARY / "09-2025-CTR.pdf"
EXEMPT = PRIMARY / "10-2025-CTR.pdf"

#: Schedule -> combined GST rate. CGST is half; the notification states CGST.
SCHEDULE_SLAB: dict[str, str] = {
    "I": "5",
    "II": "18",
    "III": "40",
    "IV": "3",
    "V": "0.25",
    "VI": "1.5",
    # VII (14% CGST / 28% GST) was omitted by Notification 19/2025 from
    # 1 Feb 2026. A heading found only there has no current rated entry.
    "VII": None,
}

_SCHED_HEAD = re.compile(
    r"Schedule\s+(VII|VI|V|IV|III|II|I)\s*[-–—]{0,2}\s*([\d.]+)\s*%", re.I
)


@dataclass(slots=True)
class Entry:
    schedule: str
    slab: str | None
    text: str


@dataclass(slots=True)
class Match:
    heading: str
    entries: list[Entry] = field(default_factory=list)
    exempt_entries: list[str] = field(default_factory=list)

    @property
    def ambiguous(self) -> bool:
        """More than one place it could sit — the annotator must choose."""
        return len(self.entries) + len(self.exempt_entries) > 1

    @property
    def slab(self) -> str | None:
        """The slab, only when exactly one entry exists."""
        if self.ambiguous:
            return None
        if self.exempt_entries:
            return "0"
        return self.entries[0].slab if self.entries else None

    @property
    def schedule(self) -> str | None:
        if self.ambiguous or not self.entries:
            return None
        return self.entries[0].schedule


@lru_cache(maxsize=4)
def _text(path: str) -> str:
    import logging

    import pypdf

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = pypdf.PdfReader(path)
    raw = "\n".join((p.extract_text() or "") for p in reader.pages)
    return re.sub(r"[ \t]+", " ", raw)


def _schedule_bounds(text: str) -> list[tuple[int, str]]:
    return [(m.start(), m.group(1).upper()) for m in _SCHED_HEAD.finditer(text)]


def _schedule_at(bounds: list[tuple[int, str]], pos: int) -> str | None:
    current = None
    for start, roman in bounds:
        if start <= pos:
            current = roman
        else:
            break
    return current


def _entry_text(text: str, pos: int, width: int = 240) -> str:
    """The entry around a match, trimmed to something quotable."""
    start = text.rfind(". ", max(0, pos - 160), pos)
    start = start + 2 if start != -1 else max(0, pos - 60)
    return re.sub(r"\s+", " ", text[start : pos + width]).strip()


def lookup(heading: str) -> Match | None:
    """Find `heading` in the archived notifications. None if not archived."""
    if not RATED.exists():
        return None
    heading = heading.strip()[:4]
    match = Match(heading=heading)

    rated = _text(str(RATED))
    bounds = _schedule_bounds(rated)
    # Collapse by schedule. A heading's sub-headings each match separately
    # ("3306", "3306 10 10", "3306 20 00"), and a neighbouring entry can name
    # the heading too ("8714 Parts and accessories of vehicles of heading
    # 8711"). Counting those as distinct entries would report a heading as
    # ambiguous when every match sits in the same schedule at the same rate.
    by_schedule: dict[str, str] = {}
    for m in re.finditer(rf"\b{re.escape(heading)}\b", rated):
        sched = _schedule_at(bounds, m.start())
        if sched is None:
            continue
        text = _entry_text(rated, m.start())
        # Prefer the entry that opens with the heading itself.
        if sched not in by_schedule or text.startswith(heading):
            if sched not in by_schedule or not by_schedule[sched].startswith(heading):
                by_schedule[sched] = text
    for sched, text in by_schedule.items():
        match.entries.append(Entry(sched, SCHEDULE_SLAB.get(sched), text))

    if EXEMPT.exists():
        exempt = _text(str(EXEMPT))
        seen_x: set[str] = set()
        for m in re.finditer(rf"\b{re.escape(heading)}\b", exempt):
            text = _entry_text(exempt, m.start())
            if text[:80] in seen_x:
                continue
            seen_x.add(text[:80])
            match.exempt_entries.append(text)

    return match
