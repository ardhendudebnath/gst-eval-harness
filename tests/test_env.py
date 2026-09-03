"""The .env loader.

The README has told people to copy .env.example to .env since week 1, and
nothing read it. These pin the behaviour that makes following that instruction
actually work — and the two rules that keep a dotenv loader trustworthy: a real
environment variable wins, and values are never printed.
"""

import os

import pytest

from harness import env as env_mod


def test_parses_the_ordinary_shapes():
    got = env_mod.parse(
        "# a comment\n"
        "\n"
        "NVIDIA_API_KEY=nvapi-abc123\n"
        "  SPACED = value with spaces  \n"
        'QUOTED="quoted value"\n'
        "SINGLE='single quoted'\n"
        "export EXPORTED=from-a-sourced-file\n"
        "NIM_BASE_URL=http://localhost:8000\n"
    )
    assert got == {
        "NVIDIA_API_KEY": "nvapi-abc123",
        "SPACED": "value with spaces",
        "QUOTED": "quoted value",
        "SINGLE": "single quoted",
        "EXPORTED": "from-a-sourced-file",
        "NIM_BASE_URL": "http://localhost:8000",
    }


def test_blank_values_are_dropped():
    """.env.example ships every key empty; a copied-but-unfilled file must not
    read as 'set' to anything checking membership rather than truth."""
    got = env_mod.parse("ANTHROPIC_API_KEY=\nOPENAI_API_KEY=   \nNVIDIA_API_KEY=real\n")
    assert got == {"NVIDIA_API_KEY": "real"}
    assert "ANTHROPIC_API_KEY" not in got


def test_a_bom_does_not_become_part_of_the_first_key():
    got = env_mod.parse("﻿NVIDIA_API_KEY=abc\n")
    assert got == {"NVIDIA_API_KEY": "abc"}


def test_junk_lines_are_ignored():
    assert env_mod.parse("no equals sign here\n# NOPE=1\n\n\n") == {}


def test_load_sets_the_environment(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("NVIDIA_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    assert env_mod.load(path) == ["NVIDIA_API_KEY"]
    assert os.environ["NVIDIA_API_KEY"] == "from-file"


def test_a_real_environment_variable_wins(tmp_path, monkeypatch):
    """A stale .env quietly overriding an exported key is the failure mode
    that makes dotenv loaders untrustworthy."""
    path = tmp_path / ".env"
    path.write_text("NVIDIA_API_KEY=stale-from-file\n", encoding="utf-8")
    monkeypatch.setenv("NVIDIA_API_KEY", "exported-for-this-command")

    assert env_mod.load(path) == []
    assert os.environ["NVIDIA_API_KEY"] == "exported-for-this-command"


def test_override_is_available_but_not_the_default(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("NVIDIA_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("NVIDIA_API_KEY", "exported")

    assert env_mod.load(path, override=True) == ["NVIDIA_API_KEY"]
    assert os.environ["NVIDIA_API_KEY"] == "from-file"


def test_a_missing_file_is_not_an_error(tmp_path):
    assert env_mod.load(tmp_path / "nope.env") == []


def test_load_returns_names_never_values(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("NVIDIA_API_KEY=super-secret-value\n", encoding="utf-8")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    assert "super-secret-value" not in repr(env_mod.load(path))


def test_the_shipped_example_parses(tmp_path):
    """The file the README tells people to copy must survive the parser."""
    from pathlib import Path

    example = Path(".env.example")
    if not example.is_file():
        pytest.skip("run from the repo root")
    # Every key is blank in the example, so nothing should be extracted.
    assert env_mod.parse(example.read_text(encoding="utf-8")) == {
        "NIM_BASE_URL": "http://localhost:8000"
    }
