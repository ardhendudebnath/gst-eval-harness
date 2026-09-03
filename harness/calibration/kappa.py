"""Cohen's kappa and confusion matrices, stdlib-only.

Used twice, deliberately by the same code path:

  * Week 3 — annotator vs their own re-labels (the self-agreement ceiling).
  * Week 5 — LLM judge vs human labels (the number the README lives or dies on).

Reusing one implementation means the judge is held to exactly the measure the
human was, which is the whole point of calibration.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Sequence

# Landis & Koch bands, as reported in the README.
BANDS: tuple[tuple[float, str], ...] = (
    (0.40, "Unusable. Fix the rubric."),
    (0.60, "Moderate. Usable with caveats — state them."),
    (0.80, "Substantial. This is a good result."),
    (1.01, "Strong — but check the task has not been made trivially easy."),
)


def interpret(k: float) -> str:
    for threshold, reading in BANDS:
        if k < threshold:
            return reading
    return BANDS[-1][1]


@dataclass(slots=True)
class Agreement:
    n: int
    observed: float
    expected: float
    kappa: float
    labels: list[str]
    matrix: dict[tuple[str, str], int]

    @property
    def reading(self) -> str:
        return interpret(self.kappa)

    def render_matrix(self, *, row_name: str = "A", col_name: str = "B") -> str:
        """Confusion matrix as fixed-width text, ready to paste into a README."""
        corner = row_name + " \\ " + col_name
        width = max(6, len(corner) + 1, max((len(x) for x in self.labels), default=6) + 1)
        head = f"{corner:<{width}}" + "".join(
            f"{lab:>{width}}" for lab in self.labels
        )
        lines = [head, "-" * len(head)]
        for r in self.labels:
            row = f"{r:<{width}}" + "".join(
                f"{self.matrix.get((r, c), 0):>{width}}" for c in self.labels
            )
            lines.append(row)
        return "\n".join(lines)


def cohens_kappa(a: Sequence[str], b: Sequence[str]) -> Agreement:
    """Cohen's kappa between two sequences of categorical labels.

    kappa = (po - pe) / (1 - pe), where po is observed agreement and pe is the
    agreement expected from the two raters' marginal distributions alone.
    """
    if len(a) != len(b):
        raise ValueError(f"length mismatch: {len(a)} vs {len(b)}")
    n = len(a)
    if n == 0:
        raise ValueError("no paired labels")

    labels = sorted(set(a) | set(b))
    matrix = Counter(zip(a, b))

    observed = sum(1 for x, y in zip(a, b) if x == y) / n

    count_a, count_b = Counter(a), Counter(b)
    expected = sum(
        (count_a.get(lab, 0) / n) * (count_b.get(lab, 0) / n) for lab in labels
    )

    # Perfect agreement with a single label used throughout: kappa is undefined
    # (0/0). Report 1.0 and let the caller notice n and the label count.
    kappa = 1.0 if expected >= 1.0 else (observed - expected) / (1.0 - expected)

    return Agreement(
        n=n,
        observed=observed,
        expected=expected,
        kappa=kappa,
        labels=labels,
        matrix=dict(matrix),
    )
