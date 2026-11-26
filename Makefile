# Convenience wrappers. On Windows without make, run the python commands directly.
PY ?= python

.PHONY: setup smoke validate radio film offline report

setup:
	$(PY) -m pip install -r requirements.txt

smoke:
	$(PY) -m pipeline.smoke

validate:
	$(PY) -m pipeline.validate

radio:
	$(PY) film.py --radio

film:
	$(PY) film.py

offline:
	$(PY) film.py --offline

report:
	$(PY) -m pipeline.report --write
