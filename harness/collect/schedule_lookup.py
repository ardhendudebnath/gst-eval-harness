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

#: Notification 19/2025, in force 1 February 2026, transcribed from the
#: archived copy in `data/reference/primary/19-2025-CTR.pdf`.
#:
#: It did not merely delete Schedule VII. It moved every entry, and split one:
#:
#:   (a) Schedule II – 9%:  "4A. 2403 19 21, 2403 19 29 Biris"
#:   (b) Schedule III – 20%: serials 14-19, pan masala and the rest of tobacco
#:   (c) "the Schedule VII – 14%, and the entries relating thereto shall be
#:        omitted"
#:
#: Reading 9/2025 alone therefore reports "no current rated entry" for six
#: headings whose current rate is 40% — or 18% for biris, which is the whole
#: point of the split and the sharpest rate-changed example in the corpus.
#:
#: Transcribed rather than parsed: the amending prose is three sentences of
#: legal drafting and a regex over it would be far more fragile than this
#: table. `tests/test_notification_19.py` checks every row below against the
#: archived text, so the transcription cannot drift from the document.
AMENDED_2026: dict[str, list[tuple[str, str, str]]] = {
    # heading -> [(sub-heading or "", schedule, description)]
    "2106": [("2106 90 20", "III", "Pan masala")],
    "2401": [("", "III", "Unmanufactured tobacco; tobacco refuse "
                          "[other than tobacco leaves]")],
    "2402": [("", "III", "Cigars, cheroots, cigarillos and cigarettes, of "
                          "tobacco or of tobacco substitutes")],
    "2403": [
        ("2403 19 21, 2403 19 29", "II", "Biris"),
        ("2403 (other than 2403 19 21, 2403 19 29)", "III",
         "Other manufactured tobacco and manufactured tobacco substitutes; "
         "homogenised or reconstituted tobacco; tobacco extracts and essences "
         "[other than biris]"),
    ],
    "2404": [
        ("2404 11 00", "III", "Products containing tobacco or reconstituted "
                              "tobacco and intended for inhalation without "
                              "combustion"),
        ("2404 19 00", "III", "Products containing tobacco or nicotine "
                              "substitutes and intended for inhalation "
                              "without combustion"),
    ],
}


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
    #: Chapter-level entries, found only when the heading itself is not listed.
    #: Never resolve a slab — they are a pointer for the annotator, not a
    #: determination. See `chapter_only`.
    chapter_entries: list[Entry] = field(default_factory=list)

    @property
    def _outcomes(self) -> set[str | None]:
        """The distinct slabs this heading could attract.

        Counting *entries* rather than outcomes reports a heading as ambiguous
        when every entry gives the same answer — 2404 has two sub-headings and
        both are 40%, so which one applies changes nothing about the rate.
        """
        found: set[str | None] = {e.slab for e in self.entries}
        if self.exempt_entries:
            found.add("0")
        if not self.entries and not self.exempt_entries:
            found |= {e.slab for e in self.chapter_entries}
        return found

    @property
    def ambiguous(self) -> bool:
        """More than one *rate* it could attract — the annotator must choose."""
        return len(self._outcomes) > 1

    @property
    def chapter_only(self) -> bool:
        """The heading is absent, but its chapter is specified.

        The schedules describe a great deal of the tariff at chapter level —
        "63 [other than 6305 32 00, 6305 33 00, 6309] Other made up textile
        articles" — so a heading with no entry of its own is usually covered
        rather than unlisted. Reporting "not found" for those was wrong, and
        wrong in the direction that matters: it reads as "the notification is
        silent" when the notification is not silent at all.
        """
        return not self.entries and not self.exempt_entries and bool(self.chapter_entries)

    @property
    def slab(self) -> str | None:
        """The slab, only when every entry agrees on it.

        A chapter-level entry never resolves one even when unanimous: it
        carries exclusions, and whether these goods fall inside them is a
        reading of the entry, not a lookup.
        """
        if self.ambiguous or self.chapter_only:
            return None
        outcomes = self._outcomes
        return next(iter(outcomes)) if len(outcomes) == 1 else None

    @property
    def decides_it(self) -> str | None:
        """The condition the competing entries turn on, in the Gazette's words.

        These schedules are almost always built the same way: one entry
        enumerates particular goods at a lower rate, and another sweeps up the
        rest while excluding them by name. 3307 is 5% for "Shaving cream,
        shaving lotion, aftershave lotion" and 18% for everything else in the
        heading; 8708 is 5% for four listed tractor parts and 18% for
        "[other than specified parts of tractors]".

        So the exclusion clause states the axis outright, and surfacing it
        turns the annotator's job from "read two schedule extracts and work out
        what separates them" into "is this good one of these?". Returns None
        when no entry carries one — then the extracts are all there is.
        """
        if not self.ambiguous:
            return None
        clauses: list[str] = []
        for source in ([e.text for e in self.entries] + self.exempt_entries):
            for m in _EXCLUSION.finditer(source):
                # Truncated only when the *entry* was cut short, which
                # `_entry_text` marks. A clause that simply ends where its
                # entry ends is complete, and dropping its last word turned
                # "rice bran" into "rice".
                rest = source[m.end():].lstrip()
                clause = _tidy_clause(m.group(1), truncated=rest.startswith("…"))
                if clause and clause.lower() not in {c.lower() for c in clauses}:
                    clauses.append(clause)
        if not clauses:
            return None
        # Each clause is capped, but a heading with several of them can still
        # join into a paragraph. Two conditions is a discriminator; five is an
        # extract, and the entries are already shown in full.
        joined = "; ".join(clauses[:3])
        return joined if len(joined) <= 200 else joined[:197].rsplit(" ", 1)[0] + " …"

    @property
    def schedule(self) -> str | None:
        """The schedule, when the entries agree on both rate and schedule."""
        if self.ambiguous or not self.entries:
            return None
        schedules = {e.schedule for e in self.entries}
        return next(iter(schedules)) if len(schedules) == 1 else None


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


#: The next entry begins with its serial number: "250. 3307 41 00 Agarbatti".
#: Used to end an entry where the schedule ends it.
_NEXT_SERIAL = re.compile(r"\s\d{1,3}\s*\.\s+(?=\d{4}|\d{2}\b|[A-Z])")

#: "[other than specified parts of tractors]", "other than charger or charging
#: station for Electrically operated vehicles". Both bracketed and bare forms
#: appear, and the clause names exactly the goods that change schedule.
#: The ellipsis is excluded so `_entry_text`'s own truncation marker cannot be
#: swallowed into the clause — when that happened the clause ended "...24 …"
#: and neither the serial-stripping nor the truncation test could see it.
#: A closing paren ends it too: "(other than medicaments) including sunscreen
#: ..." is an exclusion of medicaments, and running past the paren swept the
#: whole following list into the clause.
_EXCLUSION = re.compile(r"other\s+than\s+([^\].;…)]{3,160})", re.I)

#: A serial number left on the end of a clause when the entry was cut there —
#: "...not to be used as fertilizers 24".
_TRAILING_SERIAL = re.compile(r"\s+\d{1,3}\s*$")


def _tidy_clause(raw: str, *, truncated: bool) -> str:
    """Make an exclusion clause readable, and honest about being cut short.

    The entry text ends at the next serial number, so a clause running past
    that boundary arrives chopped — sometimes mid-word ("shaving cream,
    shavin"). Silently presenting the fragment invites an annotator to read it
    as the whole condition, so a cut clause loses its partial last word and
    says it is incomplete.
    """
    clause = _TRAILING_SERIAL.sub("", re.sub(r"\s+", " ", raw)).strip(" ,.;]")
    if truncated:
        # The ellipsis alone says the clause is cut. An earlier version also
        # dropped the last word to handle a half-word like "shavin", but that
        # cost a whole word from every clause that merely ended where its
        # entry ended — "rice bran" became "rice".
        clause += " …"
    # A clause this long has stopped being a discriminator and become an
    # extract; the entry text is already shown, so cut it rather than repeat.
    if len(clause) > 120:
        clause = clause[:117].rsplit(" ", 1)[0] + " …"
    return clause.strip()


def _entry_text(text: str, pos: int, width: int = 320) -> str:
    """The entry around a match, ending where the next serial number begins.

    A fixed window runs straight into the following entries, so the extract
    for heading 3307 arrived carrying serials 250 and 251 — text about
    agarbatti and toilet soap, which are different headings entirely. An
    annotator reading that has to work out which words belong to their goods
    before they can start on the actual question.
    """
    start = text.rfind(". ", max(0, pos - 160), pos)
    start = start + 2 if start != -1 else max(0, pos - 60)
    chunk = re.sub(r"\s+", " ", text[start : pos + width]).strip()

    # Cut at the first serial that starts after this entry's own heading. The
    # offset skips the heading itself, which is digits too.
    cut = _NEXT_SERIAL.search(chunk, 12)
    if cut:
        return chunk[: cut.start()].strip()
    # No serial found means the window ran out mid-entry. Say so: an extract
    # that stops mid-sentence should not be read as the whole condition.
    ended_naturally = len(text) <= pos + width
    return chunk.strip() + ("" if ended_naturally else " …")


#: A chapter number carrying goods. Every genuine chapter entry in these
#: schedules is introduced by its serial number — "390. 63 [other than
#: 6305 32 00, 6305 33 00, 6309] Other made up textile articles", "36. 29 All
#: organic chemicals" — and requiring that is what separates a chapter
#: reference from a two-digit fragment of a longer tariff code. Without it,
#: the "29" in "0101 29 Live horses" reads as chapter 29 and puts live horses
#: forward as an organic chemical.
_SERIAL = r"(?:^|[^\d])\d{1,3}\s*\.\s*"


def _chapter_entries(
    text: str, bounds: list[tuple[int, str]], chapter: str
) -> dict[str, str]:
    pattern = re.compile(
        rf"{_SERIAL}({re.escape(chapter)})\s*(?:\[[^\]]*\]\s*)?(?=[A-Z])"
    )
    by_schedule: dict[str, str] = {}
    for m in pattern.finditer(text):
        sched = _schedule_at(bounds, m.start(1))
        if sched is None or sched in by_schedule:
            continue
        by_schedule[sched] = _entry_text(text, m.start(1))
    return by_schedule


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
        # Schedule VII was omitted outright on 1 February 2026. Reporting its
        # entries as live — even at slab None — offers the annotator a rate
        # that no longer exists, which is the exact error this project exists
        # to measure. The replacements come from AMENDED_2026 below.
        if sched == "VII":
            continue
        match.entries.append(Entry(sched, SCHEDULE_SLAB.get(sched), text))

    for sub, sched, description in AMENDED_2026.get(heading, []):
        label = f"{sub or heading} {description}"
        match.entries.append(
            Entry(sched, SCHEDULE_SLAB.get(sched),
                  f"[Notification 19/2025, in force 2026-02-01] {label}")
        )

    # Only when the heading itself is absent. A heading that has its own entry
    # is governed by it, and dragging in the chapter would invent competition.
    if not match.entries:
        for sched, text in _chapter_entries(rated, bounds, heading[:2]).items():
            match.chapter_entries.append(Entry(sched, SCHEDULE_SLAB.get(sched), text))

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
