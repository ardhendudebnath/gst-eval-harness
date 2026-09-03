"""`leaderboard.main()` against result files on disk.

This runs immediately after the paid calls in `harness.run`, and no test called
it — the same coverage gap that hid a NameError in the open-weight runner. The
existing leaderboard tests exercise `render()` with hand-built objects, which
says nothing about whether the function that reads the directory works.
"""

from __future__ import annotations

import json

import pytest

from harness.report import leaderboard
from harness.report.results import RunResult, load_all


def a_run(key="opus-5", *, slab_acc=0.8, stale=0.1, started="2026-09-04T10:00:00+00:00",
          mode="shared", n=20):
    # Mirror new_run_id's second-granularity stamp. Truncating to the date
    # would give two runs of one model the same filename, and the second would
    # overwrite the first on disk.
    stamp = started[:19].replace("-", "").replace(":", "")
    return RunResult(
        run_id=f"{stamp}_{key}_{mode}",
        model_key=key,
        model_id=f"vendor/{key}",
        served_model_id=f"vendor/{key}",
        provider="anthropic",
        tier="frontier",
        prompt_version="v1",
        prompt_mode=mode,
        dataset_sha="abc123",
        dataset_n=n,
        started_at=started,
        finished_at=started,
        summary={"n": n, "slab_acc": slab_acc, "stale_slab_rate": stale,
                 "stale_by_slab": {"28": 2}, "errored": 0, "unparseable": 0,
                 "hsn_acc": 0.7},
        cost={"correct": int(slab_acc * n), "total_usd": 0.42,
              "cost_per_correct_usd": 0.03, "tokens_in": 14000, "tokens_out": 5000},
        rows=[],
    )


@pytest.fixture
def results_dir(tmp_path, monkeypatch):
    d = tmp_path / "results"
    d.mkdir()
    monkeypatch.setattr("harness.report.results.RESULTS", d)
    monkeypatch.setattr("harness.report.leaderboard.OUT", d / "leaderboard.html")
    monkeypatch.chdir(tmp_path)
    return d


def test_main_writes_a_page_from_files_on_disk(results_dir):
    a_run("opus-5", slab_acc=0.9).save(results_dir)
    a_run("open-weight", slab_acc=0.55, stale=0.30).save(results_dir)

    assert leaderboard.main() == 0

    html = (results_dir / "leaderboard.html").read_text(encoding="utf-8")
    assert "opus-5" in html and "open-weight" in html
    assert "<table" in html.lower()


def test_main_says_so_rather_than_rendering_zeros(results_dir, capsys):
    assert leaderboard.main() == 0
    out = capsys.readouterr().out
    assert "0 model(s) ranked" in out and "no runs yet" in out
    # The page must still exist and must not imply a measured result.
    html = (results_dir / "leaderboard.html").read_text(encoding="utf-8")
    assert "0.0%" not in html


def test_the_stale_slab_rate_reaches_the_page(results_dir):
    """The headline column. If it is dropped in rendering, the finding is lost."""
    a_run("open-weight", stale=0.35).save(results_dir)
    leaderboard.main()
    html = (results_dir / "leaderboard.html").read_text(encoding="utf-8")
    assert "35.0%" in html
    assert "stale" in html.lower()


def test_a_rerun_appears_once_at_its_current_score(results_dir):
    a_run("opus-5", slab_acc=0.50, started="2026-09-04T09:00:00+00:00").save(results_dir)
    a_run("opus-5", slab_acc=0.95, started="2026-09-04T11:00:00+00:00").save(results_dir)

    runs = load_all(results_dir)
    assert len(runs) == 2  # both kept on disk
    leaderboard.main()
    html = (results_dir / "leaderboard.html").read_text(encoding="utf-8")
    assert "95.0%" in html and "50.0%" not in html


def test_a_stray_json_does_not_take_the_leaderboard_down(results_dir, capsys):
    """`results/` is a committed directory people put things in."""
    a_run("opus-5").save(results_dir)
    (results_dir / "notes.json").write_text('{"todo": "rerun this"}', encoding="utf-8")
    (results_dir / "list.json").write_text("[1, 2, 3]", encoding="utf-8")

    runs = load_all(results_dir)

    assert len(runs) == 1
    err = capsys.readouterr().err
    assert "notes.json: not a run result, skipped" in err
    assert "list.json: not a run result, skipped" in err


def test_a_broken_run_file_still_raises(results_dir):
    """A run someone paid for must never be dropped silently."""
    a_run("opus-5").save(results_dir)
    bad = results_dir / "20260904T120000Z_open-weight_shared.json"
    bad.write_text('{"run_id": "x", "model_key": "y", "summary": {}, ', encoding="utf-8")

    with pytest.raises(ValueError, match="open-weight"):
        load_all(results_dir)


def test_a_run_result_missing_required_fields_raises(results_dir):
    bad = results_dir / "20260904T120000Z_open-weight_shared.json"
    bad.write_text(json.dumps({"run_id": "x", "model_key": "y", "summary": {}}),
                   encoding="utf-8")

    with pytest.raises(ValueError, match="open-weight"):
        load_all(results_dir)


def test_a_stale_dataset_is_flagged_not_ranked_silently(results_dir, monkeypatch):
    """A result fingerprinted against a different dataset must be marked."""
    a_run("opus-5").save(results_dir)  # dataset_sha="abc123"
    monkeypatch.setattr(
        "harness.report.leaderboard.dataset_fingerprint", lambda *a, **k: ("zzz999", 40)
    )
    leaderboard.main()
    html = (results_dir / "leaderboard.html").read_text(encoding="utf-8")
    assert "stale" in html.lower()
