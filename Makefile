PY ?= python3
VENV ?= .venv
BIN := $(VENV)/bin

.PHONY: setup setup-extra openmontage hyperframes fonts assets demo doctor schema test test-contracts test-snapshots test-pipelines test-qa clean

setup:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -q --upgrade pip
	$(BIN)/pip install -q -r requirements.txt
	$(BIN)/pip install -q -e .
	$(BIN)/va assets
	@echo "Setup done. Optional: make setup-extra openmontage hyperframes fonts"

setup-extra:
	$(BIN)/pip install -r requirements-extra.txt

openmontage:
	test -d OpenMontage || git clone --depth 1 https://github.com/calesthio/OpenMontage.git
	$(BIN)/pip install -r OpenMontage/requirements.txt || true
	cd OpenMontage/remotion-composer && npm install || true

hyperframes:
	npm i -g hyperframes
	npx skills add heygen-com/hyperframes
	npx skills add Leonxlnx/cinetic

fonts:
	mkdir -p assets/fonts
	for f in Anton Bangers Montserrat Inter; do \
	  curl -sfL "https://github.com/google/fonts/raw/main/ofl/$$(echo $$f | tr A-Z a-z)/$$f-Regular.ttf" -o assets/fonts/$$f-Regular.ttf \
	  || curl -sfL "https://github.com/google/fonts/raw/main/ofl/$$(echo $$f | tr A-Z a-z)/$$f%5Bwght%5D.ttf" -o assets/fonts/$$f.ttf || true; \
	done
	@ls assets/fonts

assets:
	$(BIN)/va assets

demo:
	$(BIN)/va demo

doctor:
	$(BIN)/va doctor

schema:
	$(BIN)/va schema

test: test-contracts test-qa

test-contracts:
	$(BIN)/pytest -q tests/test_contracts.py tests/test_spec.py

test-snapshots:
	$(BIN)/pytest -q -m snapshot tests

test-pipelines:
	$(BIN)/pytest -q tests/test_pipelines.py

test-qa:
	$(BIN)/pytest -q tests/test_qa.py

clean:
	rm -rf projects/demo build out
