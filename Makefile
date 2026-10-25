.DEFAULT_GOAL := help
PYTHON ?= python
NPM ?= npm
ifeq ($(OS),Windows_NT)
NPM := npm.cmd
endif
ARGS ?=

.PHONY: help test ingest build detect eval anchor api web

help:
	@echo EcoProof - ingestion, classification, batches, and testnet anchoring
	@echo test: run the offline Python tests
	@echo ingest: fetch or reuse Bronze data with ARGS - see README
	@echo build: rebuild Silver and DuckDB views with ARGS - see README
	@echo detect: classify Silver into Gold with baseline and window ARGS - see README
	@echo eval: evaluate injections on copies of Silver observations with ARGS - see README
	@echo anchor: prepare, deploy, submit, read, or verify with ARGS - see README
	@echo api: serve read-only data and verification at localhost:8000 - see README
	@echo web: serve the React/Leaflet frontend at localhost:5173 - see README

test:
	$(PYTHON) -m pytest -q

ingest:
	$(PYTHON) -m ecoproof.ingest $(ARGS)

build:
	$(PYTHON) -m ecoproof.transform $(ARGS)

detect:
	$(PYTHON) -m ecoproof.detect $(ARGS)

eval:
	$(PYTHON) -m ecoproof.detect.evaluate $(ARGS)

anchor:
	$(PYTHON) -m ecoproof.provenance.anchor $(ARGS)

api:
	$(PYTHON) -m uvicorn ecoproof.api.main:app --host 127.0.0.1 --port 8000 $(ARGS)

web:
	$(NPM) --prefix web run dev -- $(ARGS)
