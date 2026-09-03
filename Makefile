# Every target is a thin wrapper over `python -m ...`, so the repo is equally
# usable without make (Windows without a make binary, for instance).

PY ?= python

.PHONY: help collect validate strict label relabel agreement test clean

help:
	@echo "collect    fetch the raw corpus from every public source"
	@echo "collect-off  packaged-food listings only (no dependencies)"
	@echo "collect-aar  advance rulings only (needs pypdf)"
	@echo "rescreen   replay current scope filters over an existing pool"
	@echo "validate   schema + composition checks on the golden set"
	@echo "strict     as validate, but composition drift also fails (CI)"
	@echo "label      interactive labelling tool"
	@echo "relabel    blind re-label of 50 rows for self-agreement"
	@echo "agreement  score a re-label file (RELABEL=data/relabel-YYYY-MM-DD.jsonl)"
	@echo "test       unit tests"

collect: collect-off collect-aar

collect-off:
	$(PY) -m harness.collect.openfoodfacts --pages 12 --out data/raw/off.jsonl

# Older index pages carry far more text-layer PDFs; recent orders are almost
# all scans. --long raises the excerpt cap for the long_context stratum.
collect-aar:
	$(PY) -m harness.collect.aar --pages 65 --start-page 240 --out data/raw/aar.jsonl

collect-aar-long:
	$(PY) -m harness.collect.aar --pages 40 --start-page 240 --long --out data/raw/aar_long.jsonl

rescreen:
	$(PY) -m harness.collect.rescreen data/raw/off.jsonl
	$(PY) -m harness.collect.rescreen data/raw/aar.jsonl

validate:
	$(PY) -m harness.validate

strict:
	$(PY) -m harness.validate --strict

label:
	$(PY) -m harness.label.cli

relabel:
	$(PY) -m harness.label.cli --relabel 50

agreement:
	$(PY) -m harness.calibration.self_agreement --relabel $(RELABEL)

test:
	$(PY) -m pytest tests -q

clean:
	$(PY) -c "import pathlib,shutil; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"
