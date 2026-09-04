"""The isometric chart. Geometry a reader would notice if it were wrong.

Every failure pinned here was actually produced while building it: bars drawn
through the title, axis labels stacked on top of each other, "UNANSWERABLE%".
"""

from __future__ import annotations

import json
import re

import pytest

from harness.report import isometric as iso


def results(pairs, model="vendor/m", n=None):
    rows = [{"gazette_slab": g, "predicted_slab": p} for g, p in pairs]
    return {
        "model_id": model,
        "summary": {"n": n or len(rows), "stale_slab_rate": 0.25, "slab_acc": 0.5},
        "rows": rows,
    }


@pytest.fixture
def svg(tmp_path):
    src = tmp_path / "r.json"
    src.write_text(json.dumps(results([
        ("18", "18"), ("18", "18"), ("18", "28"), ("18", "12"),
        ("5", "5"), ("5", "UNANSWERABLE"), ("5", "0"),
    ])), encoding="utf-8")
    light, dark = iso.build(src, tmp_path / "out")
    return light.read_text(encoding="utf-8")


def viewbox(svg_text):
    m = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg_text)
    return int(m.group(1)), int(m.group(2))


def coords(svg_text):
    pts = []
    for poly in re.findall(r'points="([^"]+)"', svg_text):
        for pair in poly.split():
            x, y = pair.split(",")
            pts.append((float(x), float(y)))
    return pts


def test_both_themes_are_written(tmp_path):
    src = tmp_path / "r.json"
    src.write_text(json.dumps(results([("18", "18")])), encoding="utf-8")
    light, dark = iso.build(src, tmp_path / "out")
    assert light.exists() and dark.exists()
    assert light.read_text(encoding="utf-8") != dark.read_text(encoding="utf-8")


def test_the_dark_file_paints_a_dark_ground(tmp_path):
    """A transparent or light ground would make the dark README unreadable."""
    src = tmp_path / "r.json"
    src.write_text(json.dumps(results([("18", "18")])), encoding="utf-8")
    _, dark = iso.build(src, tmp_path / "out")
    assert iso.DARK["surface"] in dark.read_text(encoding="utf-8")


def test_nothing_is_drawn_above_the_header(svg):
    """Bars grow upward from the floor. With fixed top padding the tallest one
    draws straight through the title, which is what the first version did."""
    assert min(y for _, y in coords(svg)) >= iso.HEADER - 1


def test_nothing_is_drawn_outside_the_canvas(svg):
    w, h = viewbox(svg)
    xs = [x for x, _ in coords(svg)]
    ys = [y for _, y in coords(svg)]
    assert min(xs) >= 0 and max(xs) <= w
    assert min(ys) >= 0 and max(ys) <= h


def test_every_text_element_starts_inside_the_canvas(svg):
    w, h = viewbox(svg)
    for x, y in re.findall(r'<text x="([-\d.]+)" y="([-\d.]+)"', svg):
        assert 0 <= float(x) <= w, f"text at x={x} outside 0..{w}"
        assert 0 <= float(y) <= h, f"text at y={y} outside 0..{h}"


def test_axis_labels_do_not_collide(svg):
    """The predicted labels used to march half a cell left each time, so
    anything wider than that landed on its neighbour."""
    ys = {}
    for m in re.finditer(r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*>([^<]+)</text>', svg):
        x, y, label = float(m.group(1)), float(m.group(2)), m.group(3)
        if "%" not in label and label not in ("refused", "no answer"):
            continue
        for oy, ox in ys.items():
            if abs(oy - y) < 11 and abs(ox - x) < 40:
                pytest.fail(f"labels overlap near ({x}, {y}): {label}")
        ys[y] = x


def test_a_rate_gets_a_percent_sign_and_a_sentinel_does_not(svg):
    assert "UNANSWERABLE%" not in svg and "unparsed%" not in svg
    assert "refused" in svg
    assert ">18%<" in svg


def test_an_abolished_slab_is_daggered_and_uses_the_status_colour(svg):
    assert "12% †" in svg or "28% †" in svg
    assert iso.LIGHT["critical"] in svg
    # Status colour never carries meaning alone.
    assert "abolished slab" in svg


def test_every_bar_carries_its_count(svg):
    """Depth is decoration; no value should have to be read off the geometry."""
    # Six occupied cells: (18,18) twice, then five singletons.
    counts = re.findall(r'font-weight="700"[^>]*>(\d+)</text>', svg)
    assert sorted(int(c) for c in counts) == [1, 1, 1, 1, 1, 2]


def test_the_title_fits_the_canvas(svg):
    w, _ = viewbox(svg)
    title = re.search(r'font-size="20"[^>]*>([^<]+)<', svg).group(1)
    assert w >= 30 + len(title) * 10.5 - 1


def test_the_subtitle_fits_the_canvas(svg):
    """It grows when repeats add a range, and it was clipped once because the
    width was sized to the title and footnotes but not to this."""
    w, _ = viewbox(svg)
    subtitle = re.search(r'font-size="13"[^>]*>([^<]+)<', svg).group(1)
    assert w >= 30 + len(subtitle) * 6.6 - 1


def test_a_missing_results_file_is_reported_not_raised(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["isometric", "--from", str(tmp_path / "nope.json")])
    assert iso.main() == 1
    assert "no results" in capsys.readouterr().out
