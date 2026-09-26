.PHONY: dev api issuer web seed eval baseline drift reset test

# Ports come from .env (§4.3). Only the port variables are used by make itself;
# every service also loads .env on its own, so secrets never pass through make.
-include .env

MERCHANT_PORT := $(or $(MERCHANT_PORT),8000)
ISSUER_PORT := $(or $(ISSUER_PORT),8100)
WEB_PORT := $(or $(WEB_PORT),5173)

# The venv interpreter, called directly so no activation step is needed.
ifeq ($(OS),Windows_NT)
PY := .venv/Scripts/python.exe
else
PY := .venv/bin/python
endif

# Recipes avoid shell-specific syntax so they run from Git Bash, PowerShell, or cmd.

dev:
	@echo starting merchant :$(MERCHANT_PORT), issuer :$(ISSUER_PORT), web :$(WEB_PORT)
	@$(MAKE) -j3 api issuer web

api:
	$(PY) -m uvicorn api.main:app --reload --reload-dir api --port $(MERCHANT_PORT) --env-file .env

# No --reload for the issuer: on Windows the reloader repeatedly hung mid-restart
# (after loading the speaker model) and kept serving the old code without any
# sign. Restart it by hand after a backend edit: stop it, then `make issuer`.
issuer:
	$(PY) -m uvicorn issuer.main:app --port $(ISSUER_PORT) --env-file .env

web:
	npm --prefix web run dev

seed:
	$(PY) -m scripts.seed_demo

eval:
	$(PY) -m scripts.run_eval

# Needs make eval first (reuses its trials) and scripts.warm_asr (Whisper small).
baseline:
	$(PY) -m scripts.run_baseline

# Needs make eval first. Replays adaptation (§7.4) over later TORGO sessions for the Dashboard.
drift:
	$(PY) -m scripts.run_drift

reset:
	$(PY) -m scripts.reset_db
	$(MAKE) seed

test:
	$(PY) -m pytest -q
