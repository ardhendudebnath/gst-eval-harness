"""The prompt every model is given, and the parser for what comes back.

**One prompt, every model.** The project plan requires it and requires saying
so, because a leaderboard where each model got a different prompt measures
prompt-writing rather than the models. A second, per-model tuned pass is run
separately and reported alongside; the gap between the two is itself a result.

The output contract is four labelled lines rather than JSON. Across providers
that is the more robustly parseable of the two: models that have not been asked
for a JSON schema still reliably emit `SLAB: 18`, whereas free-form JSON
arrives wrapped in prose or fences often enough to cost real accuracy to
parsing rather than to classification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PROMPT_VERSION = "v1"

SYSTEM = (
    "You classify goods for Indian GST. You answer with the rate that is in "
    "force today, not a rate from an earlier schedule."
)

TEMPLATE = """\
Classify this good for Indian GST and give the applicable rate.

Product or goods description:
---
{description}
---

Answer in exactly this format, nothing else:

SLAB: <the combined GST rate as a number, one of 0, 0.25, 1.5, 3, 5, 18, 40, \
or UNANSWERABLE>
HSN: <the 4-digit HSN heading, or NONE>
ANSWERABLE: <yes or no>
WHY: <one sentence: the heading and the schedule entry that fixes the rate>

Answer UNANSWERABLE and ANSWERABLE: no only when the description does not \
determine a rate — for example when the rate turns on a fact the description \
does not state. Do not guess in that case."""


def build(description: str) -> str:
    return TEMPLATE.format(description=description.strip())


@dataclass(slots=True)
class Parsed:
    """What a model said. Not judged here — the scorers do that."""

    slab: str | None
    hsn4: str | None
    answerable: bool | None
    justification: str
    #: True when no SLAB line could be found at all, which is a different
    #: failure from answering wrongly and is reported separately.
    unparseable: bool = False


_SLAB = re.compile(r"^\s*SLAB\s*[:\-]\s*(.+?)\s*$", re.I | re.M)
_HSN = re.compile(r"^\s*HSN\s*[:\-]\s*(.+?)\s*$", re.I | re.M)
_ANS = re.compile(r"^\s*ANSWERABLE\s*[:\-]\s*(.+?)\s*$", re.I | re.M)
_WHY = re.compile(r"^\s*WHY\s*[:\-]\s*(.+?)\s*$", re.I | re.M | re.S)

_NUM = re.compile(r"(\d+(?:\.\d+)?)")
_HSN_DIGITS = re.compile(r"(\d{4})")


def _norm_slab(raw: str) -> str | None:
    """Normalise a stated rate. '18%', '18 percent', ' 18 ' all become '18'.

    Abolished rates are returned as stated rather than corrected — a model
    answering 12 or 28 is the finding this benchmark exists to measure, so the
    parser must preserve it for the scorer.
    """
    text = raw.strip()
    if re.search(r"\bUNANSWERABLE\b|\bCANNOT\b|\bUNKNOWN\b", text, re.I):
        return "UNANSWERABLE"
    m = _NUM.search(text)
    if not m:
        return None
    value = m.group(1)
    # Drop a trailing zero so "18.0" and "18" are the same label.
    if value.endswith(".0"):
        value = value[:-2]
    return value


def parse(text: str) -> Parsed:
    slab_m = _SLAB.search(text or "")
    if not slab_m:
        return Parsed(None, None, None, "", unparseable=True)

    hsn_m = _HSN.search(text)
    hsn4 = None
    if hsn_m and not re.search(r"\bNONE\b|\bN/?A\b", hsn_m.group(1), re.I):
        digits = _HSN_DIGITS.search(hsn_m.group(1))
        hsn4 = digits.group(1) if digits else None

    answerable = None
    if ans_m := _ANS.search(text):
        answerable = bool(re.search(r"\byes\b|\btrue\b", ans_m.group(1), re.I))

    slab = _norm_slab(slab_m.group(1))
    if answerable is None and slab is not None:
        answerable = slab != "UNANSWERABLE"

    why_m = _WHY.search(text)
    return Parsed(
        slab=slab,
        hsn4=hsn4,
        answerable=answerable,
        justification=" ".join((why_m.group(1) if why_m else "").split())[:600],
    )
