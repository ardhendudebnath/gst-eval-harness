"""An isometric 3D bar chart of gold slab vs predicted slab, as SVG.

Stdlib only, like the rest of this package. matplotlib would be a dependency
for one picture, and a hand-emitted SVG stays crisp at any zoom on GitHub,
which a raster export does not.

    python -m harness.report.isometric                 # from the gazette probe
    python -m harness.report.isometric --from results/<run>.json

Two files are written, light and dark, so the README can hand GitHub a
<picture> and let the reader's theme choose. A single image is always wrong for
one of the two themes.

**On 3D.** Depth is decoration here, not data: the height of a bar is the only
quantity, and an isometric view makes heights harder to compare than a flat
grid would. It earns its place by making one thing immediately visible -- the
bars standing over predicted slabs that no longer exist, in a column with no
gold counterpart at all. Every bar is directly labelled with its count so no
value has to be read off the geometry, and the same numbers appear in a table
beneath the figure in the README. If you want the honest comparison of
magnitudes, read the table.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness.schema import ABOLISHED_SLABS, SLAB_ABOLISHED_ON

# Palette roles. Status colours for the two things a bar can mean, because
# "the model quoted a dead rate" is a state, not a series.
LIGHT = {
    "surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781",
    "grid": "#e1e0d9", "axis": "#c3c2b7",
    "good": "#0ca30c", "critical": "#d03b3b", "other": "#2a78d6",
}
DARK = {
    "surface": "#1a1a19", "ink": "#ffffff", "ink2": "#c3c2b7", "muted": "#898781",
    "grid": "#2c2c2a", "axis": "#383835",
    "good": "#0ca30c", "critical": "#d03b3b", "other": "#3987e5",
}

CELL_W, CELL_D = 62.0, 34.0   # isometric footprint of one cell
UNIT_H = 26.0                 # pixels per unit of count
HEADER = 96.0                 # title + subtitle band
LEFT_GUTTER = 120.0           # room for the labels on the lower-left edge


def _shade(hex_colour: str, factor: float) -> str:
    """Lighten (>1) or darken (<1) a hex colour, for the cube's three faces."""
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    f = lambda v: max(0, min(255, int(v * factor)))  # noqa: E731
    return f"#{f(r):02x}{f(g):02x}{f(b):02x}"


def _origin(n_j: int, tallest: int) -> tuple[float, float]:
    """Where grid cell (0,0) lands on screen.

    Both components are derived, not fixed. Bars grow upward from the grid, so
    the top padding has to reserve the tallest bar's full height or the tallest
    bar draws straight through the title; and the leftmost column sits
    n_j half-cells to the left of the origin, so the left padding has to clear
    that before the axis labels get their gutter.
    """
    return (LEFT_GUTTER + n_j * CELL_W / 2, HEADER + tallest * UNIT_H)


def _iso(org: tuple[float, float], i: float, j: float, h: float = 0.0
         ) -> tuple[float, float]:
    """Grid (column, row, height) -> screen point."""
    return (
        org[0] + (i - j) * CELL_W / 2,
        org[1] + (i + j) * CELL_D / 2 - h * UNIT_H,
    )


def _slab_label(slab: str) -> str:
    """A rate gets a per-cent sign; UNANSWERABLE and unparsed do not."""
    try:
        float(slab)
    except ValueError:
        return {"UNANSWERABLE": "refused", "unparsed": "no answer"}.get(slab, slab)
    return f"{slab}%"


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _bar(org, i: int, j: int, height: float, colour: str) -> str:
    """One cube: top face plus the two visible side faces."""
    iso = lambda a, b, h=0.0: _iso(org, a, b, h)  # noqa: E731
    top = [iso(i, j, height), iso(i + 1, j, height),
           iso(i + 1, j + 1, height), iso(i, j + 1, height)]
    # Left face runs along the +j edge; right face along the +i edge.
    left = [top[0], top[3], iso(i, j + 1), iso(i, j)]
    right = [top[3], top[2], iso(i + 1, j + 1), iso(i, j + 1)]

    def poly(pts, fill):
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        return (f'<polygon points="{d}" fill="{fill}" '
                f'stroke="{fill}" stroke-width="0.5" stroke-linejoin="round"/>')

    return (poly(left, _shade(colour, 0.72))
            + poly(right, _shade(colour, 0.86))
            + poly(top, colour))


def render(matrix: dict[tuple[str, str], int], gold_slabs: list[str],
           pred_slabs: list[str], theme: dict, *, title: str, subtitle: str,
           footnote: tuple[str, ...] = ()) -> str:
    """matrix[(gold, predicted)] -> count."""
    n_i, n_j = len(gold_slabs), len(pred_slabs)
    tallest = max(matrix.values(), default=1)
    org = _origin(n_j, tallest)
    iso = lambda a, b, h=0.0: _iso(org, a, b, h)  # noqa: E731

    # Wide enough for the geometry, but never narrower than the title needs.
    # An earlier version sized to the bars alone and clipped the subtitle.
    # Footnotes wrap rather than widen: one long line drives the canvas out to
    # a width the chart does not use, stranding it in the corner.
    width = max(org[0] + n_i * CELL_W / 2 + 250, 30 + len(title) * 10.5,
                30 + len(subtitle) * 6.6,
                *(30 + len(line) * 6.4 for line in footnote or ("",)))
    # 130 covers the legend and one footnote line; each extra line needs room
    # of its own or it is drawn past the bottom edge.
    height = org[1] + (n_i + n_j) * CELL_D / 2 + 130 + max(0, len(footnote) - 1) * 17

    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
        f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'font-family="system-ui,-apple-system,Segoe UI,sans-serif">',
        f'<rect width="{width:.0f}" height="{height:.0f}" fill="{theme["surface"]}"/>',
        f'<text x="30" y="38" font-size="20" font-weight="700" '
        f'fill="{theme["ink"]}">{_esc(title)}</text>',
        f'<text x="30" y="62" font-size="13" fill="{theme["ink2"]}">{_esc(subtitle)}</text>',
    ]

    # Floor grid, so an empty cell reads as a real zero rather than absence.
    for i in range(n_i):
        for j in range(n_j):
            pts = [iso(i, j), iso(i + 1, j), iso(i + 1, j + 1), iso(i, j + 1)]
            d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
            out.append(f'<polygon points="{d}" fill="none" '
                       f'stroke="{theme["grid"]}" stroke-width="1"/>')

    # Labels go on the floor's two LOWER edges, never the upper ones. Bars only
    # ever grow upward, so nothing can be drawn over a label down here — which
    # beats putting labels beside the top edges and then fighting the occlusion
    # with halos and z-order, as an earlier version of this did.
    axis: list[str] = []
    for i, slab in enumerate(gold_slabs):                    # lower-left edge
        x, y = iso(i + 0.5, n_j + 0.45)
        axis.append(f'<text x="{x:.1f}" y="{y + 5:.1f}" text-anchor="end" font-size="14" '
                    f'font-weight="600" fill="{theme["ink2"]}">'
                    f'{_esc(_slab_label(slab))}</text>')
    # The predicted labels get a fixed column on the right with leader lines,
    # rather than marching along the edge. On the edge each one starts a half
    # cell further left than the last, so anything wider than that -- and
    # "UNANSWERABLE" is three times wider -- lands on top of its neighbour.
    label_x = org[0] + n_i * CELL_W / 2 + 74
    for j, slab in enumerate(pred_slabs):
        ex, ey = iso(n_i, j + 0.5)
        ly = org[1] + (n_i + j + 0.5) * CELL_D / 2 + 5
        dead = slab in ABOLISHED_SLABS
        colour = theme["critical"] if dead else theme["ink2"]
        label = _slab_label(slab) + (" †" if dead else "")
        axis.append(f'<path d="M{ex + 5:.1f},{ey:.1f} L{label_x - 8:.1f},{ly - 4:.1f}" '
                    f'stroke="{theme["axis"]}" stroke-width="1" fill="none"/>')
        axis.append(f'<text x="{label_x:.1f}" y="{ly:.1f}" text-anchor="start" '
                    f'font-size="13" font-weight="600" '
                    f'fill="{colour}">{_esc(label)}</text>')

    gx, gy = iso(n_i / 2, n_j + 1.6)
    axis.append(f'<text x="{gx:.1f}" y="{gy:.1f}" text-anchor="end" '
                f'font-size="11" letter-spacing="0.09em" '
                f'fill="{theme["muted"]}">GAZETTE SAYS</text>')
    axis.append(f'<text x="{label_x:.1f}" y="{org[1] + (n_i - 0.9) * CELL_D / 2:.1f}" '
                f'text-anchor="start" font-size="11" letter-spacing="0.09em" '
                f'fill="{theme["muted"]}">MODEL SAID</text>')

    # Painter's algorithm: cells further from the viewer first. Labels are held
    # back and drawn over everything, because a nearer bar would otherwise hide
    # the count belonging to the one behind it.
    labels: list[str] = []
    for i, j in sorted(((i, j) for i in range(n_i) for j in range(n_j)),
                       key=lambda c: c[0] + c[1]):
        count = matrix.get((gold_slabs[i], pred_slabs[j]), 0)
        if not count:
            continue
        pred = pred_slabs[j]
        if pred in ABOLISHED_SLABS:
            colour = theme["critical"]
        elif pred == gold_slabs[i]:
            colour = theme["good"]
        else:
            colour = theme["other"]
        out.append(_bar(org, i, j, count, colour))

        cx, cy = iso(i + 0.5, j + 0.5, count)
        labels.append(
            f'<text x="{cx:.1f}" y="{cy - 9:.1f}" text-anchor="middle" '
            f'font-size="14" font-weight="700" fill="{theme["ink"]}" '
            f'stroke="{theme["surface"]}" stroke-width="3" paint-order="stroke" '
            f'>{count}</text>'
        )
    out.extend(axis)
    out.extend(labels)

    # Legend. Status colour never carries meaning alone, so each swatch is
    # labelled, and the abolished rows are daggered on the axis as well.
    # The legend and footnote hang off the bottom edge, so extra footnote
    # lines have to lift the whole block, not just grow the canvas underneath
    # it — growing the canvas alone moves the block down with it.
    ly = height - 74 - max(0, len(footnote) - 1) * 17
    for k, (colour, label) in enumerate((
        (theme["good"], "correct"),
        (theme["critical"], "† abolished slab — no longer exists"),
        (theme["other"], "wrong, but a live slab"),
    )):
        yy = ly + k * 22
        out.append(f'<rect x="34" y="{yy - 10:.0f}" width="12" height="12" rx="2" '
                   f'fill="{colour}"/>')
        out.append(f'<text x="53" y="{yy:.0f}" font-size="13" '
                   f'fill="{theme["ink2"]}">{_esc(label)}</text>')

    for k, line in enumerate(footnote):
        out.append(f'<text x="34" y="{ly + 3 * 22 + 4 + k * 17:.0f}" font-size="12" '
                   f'fill="{theme["muted"]}">{_esc(line)}</text>')

    out.append("</svg>")
    return "\n".join(out)


def build(path: Path, out_dir: Path) -> tuple[Path, Path]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["rows"]
    gold_key = "gazette_slab" if "gazette_slab" in rows[0] else "gold_slab"

    matrix: dict[tuple[str, str], int] = {}
    for r in rows:
        pred = r.get("predicted_slab") or "unparsed"
        matrix[(r[gold_key], pred)] = matrix.get((r[gold_key], pred), 0) + 1

    def order(values):
        def key(v):
            try:
                return (0, float(v))
            except ValueError:
                return (1, 0.0)
        return sorted(values, key=key)

    gold_slabs = order({r[gold_key] for r in rows})
    pred_slabs = order({(r.get("predicted_slab") or "unparsed") for r in rows})

    summary = data["summary"]
    n = summary["n"]
    agg = data.get("aggregate")
    if agg:
        # With repeats, quote the mean and the spread. A point estimate from a
        # model that answers the same prompt differently 37% of the time
        # implies a precision the data does not have.
        m = agg["metrics"]
        subtitle = (
            f"n={n}, {agg['runs']} runs · slab accuracy "
            f"{m['slab_acc']['mean']:.0%} ({m['slab_acc']['min']:.0%}–"
            f"{m['slab_acc']['max']:.0%}) · abolished slab recited "
            f"{m['stale_cited_rate']['mean']:.0%} "
            f"({m['stale_cited_rate']['min']:.0%}–"
            f"{m['stale_cited_rate']['max']:.0%}) · {data['model_id']}"
        )
    else:
        subtitle = (f"n={n} · slab accuracy {summary['slab_acc']:.0%} · "
                    f"abolished slab answered {summary['stale_slab_rate']:.0%}, "
                    f"recited {summary.get('stale_cited_rate', 0):.0%} · "
                    f"{data['model_id']}")
    # The bars can only show the answer. A dead rate reached by way of a
    # refusal is invisible here, and that is most of them, so the number says
    # so rather than letting the geometry imply otherwise.
    footnote = [
        "† " + " · ".join(f"{s}% abolished {SLAB_ABOLISHED_ON[s]}"
                          for s in sorted(ABOLISHED_SLABS)),
        "bars show the answer only; 'recited' also counts refusals that "
        "reasoned from a dead rate",
    ]
    if agg:
        sa = agg["self_agreement"]
        footnote.append(
            f"bars are one run of {agg['runs']}; the model gave the same answer "
            f"every run for only {sa['answered_identically_every_run']} of "
            f"{sa['examples']} examples"
        )
    footnote = tuple(footnote)

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, theme in (("light", LIGHT), ("dark", DARK)):
        svg = render(matrix, gold_slabs, pred_slabs, theme,
                     title="GST slab: what the notification says vs what the model said",
                     subtitle=subtitle, footnote=footnote)
        p = out_dir / f"stale-slab-3d-{name}.svg"
        p.write_text(svg, encoding="utf-8")
        written.append(p)
        print(f"  wrote {p}")
    return tuple(written)  # type: ignore[return-value]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="src", type=Path,
                    default=Path("results/gazette_probe.json"))
    ap.add_argument("--out", type=Path, default=Path("docs"))
    args = ap.parse_args()

    if not args.src.exists():
        print(f"  no results at {args.src}")
        return 1
    build(args.src, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
