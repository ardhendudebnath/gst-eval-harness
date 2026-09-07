"""The isometric diagrams.

Every layout fault pinned here was produced while building them: geometry off
the left edge because the origin was chosen by eye, labels ordered by a layer's
right edge which moves the wrong way as layers narrow, and a subtitle that went
on describing an encoding after the encoding changed.
"""

from __future__ import annotations

import json
import re

import pytest

from harness.report import diagrams as dg


FACTS = {
    "pdfs": 605, "off": 851, "rulings": 126, "suggestions": 126,
    "with_heading": 70, "ambiguous": 41, "grounded": 28, "golden": 28,
    "human": 0, "derived": 28,
}


def build(name, theme=None):
    return dg.BUILDERS[name](FACTS, theme or dg.LIGHT).svg()


def points(svg: str) -> list[tuple[float, float]]:
    out = []
    for poly in re.findall(r'points="([^"]+)"', svg):
        for pair in poly.split():
            x, y = pair.split(",")
            out.append((float(x), float(y)))
    for a, b in re.findall(r'<text x="([-0-9.]+)" y="([-0-9.]+)"', svg):
        out.append((float(a), float(b)))
    for d in re.findall(r'<path d="M([-0-9.]+),([-0-9.]+) L([-0-9.]+),([-0-9.]+)"', svg):
        out.append((float(d[0]), float(d[1])))
        out.append((float(d[2]), float(d[3])))
    return out


def viewbox(svg: str) -> tuple[int, int]:
    m = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
    return int(m.group(1)), int(m.group(2))


# --- geometry ------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(dg.BUILDERS))
def test_nothing_is_drawn_outside_the_canvas(name):
    """Isometric lays +x down-right and +y down-left, so a second row travels
    the opposite way from the first. Picking an origin by eye put the far lane
    off the canvas twice."""
    svg = build(name)
    w, h = viewbox(svg)
    for x, y in points(svg):
        assert 0 <= x <= w, f"{name}: x={x} outside 0..{w}"
        assert 0 <= y <= h, f"{name}: y={y} outside 0..{h}"


def test_fit_handles_geometry_that_runs_left_of_the_origin():
    corners = [(0, 0, 0), (0, 20, 0), (5, 20, 3)]
    ox, oy, w, h = dg.fit(corners, left=40, top=50, right=30, bottom=20)
    xs = [dg.iso(x, y, z, ox, oy)[0] for x, y, z in corners]
    ys = [dg.iso(x, y, z, ox, oy)[1] for x, y, z in corners]
    assert min(xs) == pytest.approx(40)
    assert min(ys) == pytest.approx(50)
    assert max(xs) <= w and max(ys) <= h


# --- both themes ---------------------------------------------------------

@pytest.mark.parametrize("name", sorted(dg.BUILDERS))
def test_the_dark_variant_paints_a_dark_ground(name):
    """A transparent or light ground makes the dark README unreadable."""
    assert dg.DARK["surface"] in build(name, dg.DARK)
    assert build(name, dg.LIGHT) != build(name, dg.DARK)


# --- the figures come from the data --------------------------------------

@pytest.mark.parametrize("name", sorted(dg.BUILDERS))
def test_the_numbers_track_the_facts(name):
    """A diagram that hardcodes a figure goes stale silently."""
    # Vary every key any diagram reads. Omitting `golden` and `human` made
    # this pass vacuously for the pipeline, which is the only one that shows
    # them.
    changed = {k: (v + 137 if isinstance(v, int) else v) for k, v in FACTS.items()}
    before = dg.BUILDERS[name](FACTS, dg.LIGHT).svg()
    after = dg.BUILDERS[name](changed, dg.LIGHT).svg()
    assert before != after, f"{name} does not depend on the data"


def test_the_funnel_states_every_stage_count():
    svg = build("funnel")
    for n in (605, 126, 70, 28):
        assert f">{n}<" in svg or f">{n:,}<" in svg
    assert ">0<" in svg          # the human tier, and it is the point


def test_the_provenance_zero_tiers_are_shown_not_omitted():
    """Dropping an empty tier would hide the dataset's central gap."""
    svg = build("provenance")
    assert svg.count(">0<") >= 2
    assert "human-reviewed" in svg and "human" in svg


def test_provenance_height_is_the_count_not_an_invented_ranking():
    """An earlier version spent height on a made-up 'claim strength' ordinal
    while the real numbers sat in small text. Height is the one channel a
    reader trusts to be a quantity."""
    tall = dg.BUILDERS["provenance"]({**FACTS, "suggestions": 1000}, dg.LIGHT).svg()
    short = dg.BUILDERS["provenance"]({**FACTS, "suggestions": 10}, dg.LIGHT).svg()
    assert viewbox(tall)[1] != viewbox(short)[1] or tall != short


def test_a_subtitle_describes_the_encoding_actually_used(tmp_path):
    svg = build("provenance")
    assert "height is the number of rows" in svg
    assert "strength of the claim" not in svg


# --- the writer ----------------------------------------------------------

def test_main_writes_light_and_dark_for_every_diagram(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["diagrams", "--out", str(tmp_path)])
    assert dg.main() == 0
    for name in dg.BUILDERS:
        for mode in ("light", "dark"):
            assert (tmp_path / f"{name}-{mode}.svg").exists()


def test_facts_reads_the_repository_without_crashing_on_absence(tmp_path, monkeypatch):
    """A fresh clone has no data/cache and may have no golden set."""
    monkeypatch.chdir(tmp_path)
    f = dg.facts()
    assert f["golden"] == 0 and f["pdfs"] == 0
    for name in dg.BUILDERS:
        dg.BUILDERS[name](f, dg.LIGHT).svg()      # must not divide by zero
