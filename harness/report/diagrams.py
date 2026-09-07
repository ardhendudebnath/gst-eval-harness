"""Isometric diagrams of what this project is and where its data goes.

    python -m harness.report.diagrams

Writes a light and a dark SVG per diagram into `docs/`, so the README can hand
GitHub a <picture> and let the reader's theme choose. Stdlib only, same reason
as `isometric.py`: a vector stays crisp at any zoom and matplotlib would be a
dependency for a handful of pictures.

Three diagrams, each earning its dimension differently:

  funnel      a stack whose layers narrow toward the reader. Depth carries the
              loss at each stage, which is the whole story of the project — a
              thousand-odd source documents become 28 usable rows, and none of
              them is human-labelled yet.
  pipeline    boxes on a plane with the flow running through them. Depth
              separates the three lanes (collect / derive / evaluate) that a
              flat diagram would have to interleave.
  provenance  four steps with a wall across them. The step height is the
              claim's strength and the wall is the validator; a flat version
              would draw the wall as just another arrow.

Every figure a diagram states is read from the artefacts at build time, never
typed in, so a stale diagram is impossible — regenerate and it tells the truth
or the data changed.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from harness.report.isometric import DARK, LIGHT, _esc, _shade

# --------------------------------------------------------------------------
# isometric primitives
# --------------------------------------------------------------------------

COS30 = math.cos(math.radians(30))
SIN30 = math.sin(math.radians(30))
#: World units to pixels. One unit is one cell of the ground plane.
UNIT = 26.0


def iso(x: float, y: float, z: float, ox: float, oy: float) -> tuple[float, float]:
    """World (x right-and-down, y left-and-down, z up) to screen pixels."""
    return (ox + (x - y) * COS30 * UNIT,
            oy + (x + y) * SIN30 * UNIT - z * UNIT)


def fit(corners: list[tuple[float, float, float]], *, left: float, top: float,
        right: float, bottom: float) -> tuple[float, float, float, float]:
    """Origin and canvas size that contain every corner, with the given margins.

    Isometric lays +x down-right and +y down-left, so a second row of anything
    travels left while the first travels right. Choosing an origin by eye puts
    the far lane off the canvas — which it did, twice — and the fix is to
    project everything first and derive the origin from the bounds.
    """
    xs = [iso(x, y, z, 0, 0)[0] for x, y, z in corners]
    ys = [iso(x, y, z, 0, 0)[1] for x, y, z in corners]
    ox, oy = left - min(xs), top - min(ys)
    return ox, oy, (max(xs) - min(xs)) + left + right, (max(ys) - min(ys)) + top + bottom


def box_corners(x: float, y: float, z: float, w: float, d: float, h: float
                ) -> list[tuple[float, float, float]]:
    return [(x, y, z), (x + w, y, z), (x, y + d, z), (x + w, y + d, z),
            (x, y, z + h), (x + w, y, z + h), (x, y + d, z + h), (x + w, y + d, z + h)]


def _poly(points: list[tuple[float, float]], fill: str, stroke: str = "",
          width: float = 0.6) -> str:
    d = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    edge = stroke or fill
    return (f'<polygon points="{d}" fill="{fill}" stroke="{edge}" '
            f'stroke-width="{width}" stroke-linejoin="round"/>')


def cuboid(x: float, y: float, z: float, w: float, d: float, h: float,
           colour: str, ox: float, oy: float, *, stroke: str = "") -> str:
    """A box with its near-left and near-right faces shaded."""
    p = lambda a, b, c: iso(a, b, c, ox, oy)  # noqa: E731
    top = [p(x, y, z + h), p(x + w, y, z + h),
           p(x + w, y + d, z + h), p(x, y + d, z + h)]
    left = [top[0], top[3], p(x, y + d, z), p(x, y, z)]
    right = [top[3], top[2], p(x + w, y + d, z), p(x, y + d, z)]
    return (_poly(left, _shade(colour, 0.70), stroke)
            + _poly(right, _shade(colour, 0.85), stroke)
            + _poly(top, colour, stroke))


def text(x: float, y: float, s: str, *, size: float = 13, fill: str = "#000",
         anchor: str = "start", weight: str = "400", spacing: str = "",
         halo: str = "") -> str:
    extra = f' letter-spacing="{spacing}"' if spacing else ""
    if halo:
        extra += f' stroke="{halo}" stroke-width="3" paint-order="stroke"'
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
            f'font-size="{size}" font-weight="{weight}" fill="{fill}"{extra}>'
            f'{_esc(s)}</text>')


@dataclass
class Canvas:
    width: float
    height: float
    theme: dict
    title: str
    subtitle: str
    parts: list[str]

    def svg(self) -> str:
        head = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width:.0f}" '
            f'height="{self.height:.0f}" viewBox="0 0 {self.width:.0f} '
            f'{self.height:.0f}" font-family="system-ui,-apple-system,'
            f'Segoe UI,sans-serif">',
            f'<rect width="{self.width:.0f}" height="{self.height:.0f}" '
            f'fill="{self.theme["surface"]}"/>',
            text(30, 38, self.title, size=20, weight="700",
                 fill=self.theme["ink"]),
            text(30, 62, self.subtitle, size=13, fill=self.theme["ink2"]),
        ]
        return "\n".join(head + self.parts + ["</svg>"])


# --------------------------------------------------------------------------
# the numbers, read from the artefacts
# --------------------------------------------------------------------------

def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def facts() -> dict:
    """Everything the diagrams state. Read, never typed."""
    aar = _rows(Path("data/raw/aar.jsonl"))
    off = _rows(Path("data/raw/off.jsonl"))
    fp = _rows(Path("data/first_pass.jsonl"))
    gold = _rows(Path("data/golden.jsonl"))
    cache = list(Path("data/cache/aar").glob("*.pdf"))

    by_prov = Counter(r.get("labelled_by", "?") for r in gold)
    return {
        "pdfs": len(cache),
        "off": len(off),
        "rulings": len(aar),
        "suggestions": len(fp),
        "with_heading": sum(1 for r in fp if r.get("hsn4")),
        "ambiguous": sum(1 for r in fp
                         if (r.get("model_notes") or {}).get("slab_alternatives")),
        "grounded": sum(1 for r in fp
                        if r.get("slab") != "UNCERTAIN" and r.get("hsn4")),
        "golden": len(gold),
        "human": by_prov.get("human", 0) + by_prov.get("human-reviewed", 0),
        "derived": by_prov.get("gazette-derived", 0),
    }


# --------------------------------------------------------------------------
# diagram 1 — the funnel
# --------------------------------------------------------------------------

def funnel(f: dict, theme: dict) -> Canvas:
    """Where the source documents go. Each layer is what survives one stage."""
    stages = [
        (f["pdfs"], "ruling PDFs fetched and cached", theme["other"],
         "roughly half are scans with no text layer"),
        (f["rulings"], "rulings kept as goods classification", theme["other"],
         "services, immovable property, withdrawals and duplicates screened out"),
        (f["with_heading"], "carry a heading from the authority's own holding",
         theme["other"], "the rest state no tariff heading in the operative ruling"),
        (f["grounded"], "resolve to exactly one entry in the Gazette",
         theme["good"], f"{f['ambiguous']} span several schedules — a judgement, not a lookup"),
        (f["human"], "confirmed by a human", theme["critical"],
         "the dataset's central claim, and it is still zero"),
    ]
    top = max(s[0] for s in stages) or 1

    # Width is sqrt-scaled. Linear turns everything after the first layer into
    # a sliver — 605 to 126 is a fivefold drop and the last three layers become
    # indistinguishable, which hides exactly the part that matters.
    max_w, depth, gap, thick = 13.0, 2.4, 1.5, 0.55
    row_h = 62.0          # label rows are evenly spaced in screen space

    def geometry(i: int, n: int) -> tuple[float, float, float]:
        w = max(max_w * math.sqrt(n / top), 1.6) if n else 1.6
        return (max_w - w) / 2, i * (depth + gap), w

    geom = [geometry(i, s[0]) for i, s in enumerate(stages)]
    corners = [c for x, y, w in geom for c in box_corners(x, y, 0, w, depth, thick)]
    # Right margin is filled in below, once the label column is known.
    ox, oy, _, _ = fit(corners, left=40, top=140, right=0, bottom=0)

    # The label column clears the widest layer. The first layer is five times
    # the second, so it reaches much further right than the taper suggests.
    right_edge = max(iso(x + w, y, thick, ox, oy)[0] for x, y, w in geom)
    label_x = right_edge + 120
    parts, leaders, labels = [], [], []

    for i, (n, label, colour, note) in enumerate(stages):
        x, y, w = geom[i]
        shade = colour if n else theme["grid"]
        parts.append(cuboid(x, y, 0, w, depth, thick, shade, ox, oy))

        # Labels sit in a fixed column at evenly spaced heights. Anchoring
        # them to the layer's own right edge puts them out of order, because
        # that edge moves left faster than the layer moves down.
        ly = oy + 40 + i * row_h
        ex, ey = iso(x + w, y + depth / 2, thick, ox, oy)
        leaders.append(f'<path d="M{ex + 6:.1f},{ey:.1f} L{label_x - 92:.1f},'
                       f'{ly - 4:.1f}" stroke="{theme["axis"]}" '
                       f'stroke-width="1" fill="none"/>')
        tone = colour if n else theme["critical"]
        labels.append(text(label_x - 82, ly, f"{n:,}", size=18, weight="700",
                           fill=tone, anchor="end"))
        labels.append(text(label_x - 70, ly - 5, label, size=13,
                           fill=theme["ink"]))
        labels.append(text(label_x - 70, ly + 12, note, size=11,
                           fill=theme["muted"]))

    parts.extend(leaders)
    parts.extend(labels)
    # Size to the longest string actually present. A fixed right margin clips
    # the moment a stage description grows.
    longest = max(len(s[1]) * 7.2 for s in stages)
    longest = max(longest, max(len(s[3]) * 5.9 for s in stages))
    lowest = max(iso(x, y + depth, 0, ox, oy)[1] for x, y, w in geom)
    return Canvas(
        width=label_x - 70 + longest + 40,
        height=max(oy + 40 + len(stages) * row_h + 40, lowest + 60),
        theme=theme, parts=parts,
        title="From source documents to usable examples",
        subtitle="every figure read from the repository at build time · widths are square-root scaled",
    )


# --------------------------------------------------------------------------
# diagram 2 — the pipeline
# --------------------------------------------------------------------------

def pipeline(f: dict, theme: dict) -> Canvas:
    """Three lanes, separated by depth rather than interleaved on a plane."""
    lanes = [
        ("COLLECT", theme["other"], [
            ("GST Council index", "97(2)(a) rulings"),
            ("aar.py", "screen: services, land, scans"),
            ("normalise.py", "redact party detail"),
        ]),
        ("DERIVE", theme["good"], [
            ("ruling_outcome.py", "heading from the holding"),
            ("schedule_lookup.py", "slab from the Gazette"),
            ("golden.jsonl", f"{f['golden']} rows, {f['human']} human"),
        ]),
        ("EVALUATE", theme["critical"], [
            ("run.py", "one prompt, every model"),
            ("scorers/exact.py", "slab, HSN, staleness"),
            ("leaderboard.html", "ranked by cost per correct"),
        ]),
    ]

    bw, bd, bh, gapx, gapy = 4.6, 2.6, 0.9, 1.6, 2.6

    placed = [(li, bi, bi * (bw + gapx), li * (bd + gapy), lane, colour, name, note)
              for li, (lane, colour, boxes) in enumerate(lanes)
              for bi, (name, note) in enumerate(boxes)]
    corners = [c for _, _, x, y, *_ in placed for c in box_corners(x, y, 0, bw, bd, bh)]
    corners += [(-1.4, y, 0) for _, _, _, y, *_ in placed]      # lane captions
    ox, oy, width, height = fit(corners, left=120, top=140, right=60, bottom=60)

    parts: list[str] = []
    labels: list[str] = []
    seen_lanes: set[int] = set()

    # Painter's order: a box further from the viewer must be drawn first, and
    # distance here is x + y.
    for li, bi, x, y, lane, colour, name, note in sorted(placed, key=lambda p: p[2] + p[3]):
        parts.append(cuboid(x, y, 0, bw, bd, bh, colour, ox, oy))
        cx, cy = iso(x + bw / 2, y + bd / 2, bh, ox, oy)
        labels.append(text(cx, cy - 2, name, size=12, weight="600",
                           fill=theme["ink"], anchor="middle", halo=theme["surface"]))
        labels.append(text(cx, cy + 14, note, size=10, fill=theme["ink2"],
                           anchor="middle", halo=theme["surface"]))
        if bi < 2:
            a = iso(x + bw + 0.15, y + bd / 2, bh / 2, ox, oy)
            b = iso(x + bw + gapx - 0.15, y + bd / 2, bh / 2, ox, oy)
            parts.append(f'<path d="M{a[0]:.1f},{a[1]:.1f} L{b[0]:.1f},{b[1]:.1f}" '
                         f'stroke="{theme["axis"]}" stroke-width="1.6" fill="none"/>')
        if li not in seen_lanes:
            seen_lanes.add(li)
            lx, ly = iso(-1.4, y + bd / 2, 0, ox, oy)
            labels.append(text(lx, ly + 4, lane, size=11, spacing="0.10em",
                               fill=theme["muted"], anchor="end"))

    parts.extend(labels)
    return Canvas(width=width, height=height, theme=theme, parts=parts,
                  title="How the harness is put together",
                  subtitle="collect, derive, evaluate — the quarantine sits between lanes two and three")


# --------------------------------------------------------------------------
# diagram 3 — provenance
# --------------------------------------------------------------------------

def provenance(f: dict, theme: dict) -> Canvas:
    """Four tiers, with height carrying the count.

    An earlier version made height an invented "strength of claim" ordinal.
    Height is the one channel a reader trusts to be a quantity, so spending it
    on a made-up ranking while the real numbers sat in small text was the wrong
    way round. The two human tiers being flat *is* the finding.
    """
    tiers = [
        ("model-first-pass", f["suggestions"], theme["critical"],
         "quarantined — the validator refuses it"),
        ("gazette-derived", f["derived"], theme["other"],
         "document lookup, no human confirmed it"),
        ("human-reviewed", 0, theme["good"], "a suggestion an annotator accepted"),
        ("human", 0, theme["good"], "judged directly by the annotator"),
    ]
    top = max(t[1] for t in tiers) or 1
    bw, bd, gap = 3.2, 3.2, 2.6      # a wide gap: tall boxes hide short ones

    def height_of(n: int) -> float:
        return 0.35 + 4.2 * math.sqrt(n / top) if n else 0.18

    corners = [c for i, t in enumerate(tiers)
               for c in box_corners(i * (bw + gap), 0, 0, bw, bd, height_of(t[1]))]
    ox, oy, width, height = fit(corners, left=70, top=150, right=150, bottom=130)
    parts: list[str] = []

    for i, (name, n, colour, note) in enumerate(tiers):
        x = i * (bw + gap)
        h = height_of(n)
        shade = colour if n else theme["grid"]
        parts.append(cuboid(x, 0, 0, bw, bd, h, shade, ox, oy))
        cx, cy = iso(x + bw / 2, bd / 2, h, ox, oy)
        parts.append(text(cx, cy - 10, f"{n:,}", size=19, weight="700",
                          fill=colour if n else theme["critical"],
                          anchor="middle", halo=theme["surface"]))
        bx, by = iso(x + bw / 2, bd + 0.5, 0, ox, oy)
        parts.append(text(bx, by + 18, name, size=12, weight="600",
                          fill=theme["ink"], anchor="middle"))
        parts.append(text(bx, by + 33, note, size=10, fill=theme["muted"],
                          anchor="middle"))

    # The validator wall, between quarantine and everything admissible.
    wx = bw + gap / 2
    wall_h = height_of(top) + 0.6
    a = iso(wx, -0.4, 0, ox, oy)
    b = iso(wx, bd + 0.4, 0, ox, oy)
    c = iso(wx, bd + 0.4, wall_h, ox, oy)
    d = iso(wx, -0.4, wall_h, ox, oy)
    parts.append(_poly([a, b, c, d], "none", theme["critical"], 1.6))
    parts.append(text(d[0] + 14, min(c[1], d[1]) - 12, "validator refuses",
                      size=11, weight="600", fill=theme["critical"],
                      anchor="start"))

    return Canvas(width=width, height=height, theme=theme, parts=parts,
                  title="What a label claims, and who made it",
                  subtitle="height is the number of rows · the wall is harness/schema.py, "
                           "which rejects an unreviewed suggestion outright")


# --------------------------------------------------------------------------

BUILDERS = {"funnel": funnel, "pipeline": pipeline, "provenance": provenance}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("docs"))
    ap.add_argument("--only", choices=sorted(BUILDERS), default=None)
    args = ap.parse_args()

    f = facts()
    args.out.mkdir(parents=True, exist_ok=True)
    names = [args.only] if args.only else sorted(BUILDERS)
    for name in names:
        for mode, theme in (("light", LIGHT), ("dark", DARK)):
            canvas = BUILDERS[name](f, theme)
            path = args.out / f"{name}-{mode}.svg"
            path.write_text(canvas.svg(), encoding="utf-8")
            print(f"  wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
