"""The labelling prompt, when a shell command is typed into it.

A long session looks enough like a terminal that the next command goes into the
running program instead of the shell. The menu then rejects it as an invalid
key, so the command is neither run nor reported as unrun — and the session
quietly goes nowhere while looking like it is working.
"""

import pytest

from harness.label import cli


def answers(monkeypatch, *values):
    it = iter(values)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(it))


@pytest.mark.parametrize("text", [
    "python -m harness.label.cli --review-first-pass --exclude-state Gujarat",
    "python -m harness.run --model open-weight --limit 20",
    "git status",
    "pytest tests -q",
    "cd ../other-repo",
    ".\\venv\\Scripts\\activate",
    "./run.sh",
    "pip install -e .",
])
def test_shell_commands_are_recognised(text):
    assert cli._looks_like_a_shell_command(text)


@pytest.mark.parametrize("text", [
    "fly ash bricks",
    "quartz slabs, polished",
    "cement",                      # a bare word is never a command here
    # Every one of these opens with a real shell command and is also a
    # perfectly ordinary thing to be classifying.
    "type approval certificate",
    "cat food, 400 g pouch",
    "cd player, portable",
    "clear glass bottles, 750 ml",
    "echo cancelling headphones",
    "make up kit, assorted",
    "reads as a supply of goods",
])
def test_real_answers_are_not(text):
    assert not cli._looks_like_a_shell_command(text)


def test_the_user_is_told_rather_than_just_rejected(monkeypatch, capsys):
    answers(monkeypatch, "python -m harness.run --model open-weight", "fly ash bricks")

    assert cli._ask("  > ") == "fly ash bricks"
    out = capsys.readouterr().out
    assert "went to this program, not to your shell" in out
    assert "nothing was run" in out
    assert ":q" in out


def test_repeating_it_accepts_it_as_the_answer(monkeypatch):
    """Informing must not become trapping."""
    answers(monkeypatch, "git log --oneline", "git log --oneline")
    assert cli._ask("  > ") == "git log --oneline"


def test_a_menu_still_takes_a_normal_key(monkeypatch):
    answers(monkeypatch, "f")
    assert cli._menu("  > ", cli.SLAB_KEYS) == "18"


def test_a_menu_warns_then_takes_the_key(monkeypatch, capsys):
    answers(monkeypatch, "python -m harness.label.cli --grounded-only", "e")
    assert cli._menu("  > ", cli.SLAB_KEYS) == "5"
    assert "not to your shell" in capsys.readouterr().out


def test_quit_still_quits(monkeypatch):
    answers(monkeypatch, ":q")
    with pytest.raises(cli.Quit):
        cli._ask("  > ")


def test_ctrl_c_still_quits(monkeypatch):
    def interrupt(_prompt=""):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", interrupt)
    with pytest.raises(cli.Quit):
        cli._ask("  > ")
