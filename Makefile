.DEFAULT_GOAL := help

SHELL := /bin/bash
PYTHON ?= python3
VENV ?= .venv
VENVBIN := $(VENV)/bin
PYTHON_BIN := $(VENVBIN)/python
INSTALL_STAMP := $(VENV)/.installed
ENV_FILE ?= .env
APP_HOST ?= 0.0.0.0
APP_PORT ?= 8000
APP_MODULE ?= main:app
TORCH_INDEX_URL ?= https://download.pytorch.org/whl/cu124
TORCH_VERSION ?= 2.5.1
TORCHVISION_VERSION ?= 0.20.1
TORCHAUDIO_VERSION ?= 2.5.1

export PYTHONPATH := $(PWD)

.PHONY: help setup env run worker check-gpu test lint format typecheck clean dist-clean docker-gpu docker-down docker-test docker-logs docker-shell redis-up redis-down

help:
	@echo "Available targets:"
	@printf "  %-18s %s\n" "setup" "Create venv and install Python deps"
	@printf "  %-18s %s\n" "env" "Create .env from template if missing"
	@printf "  %-18s %s\n" "run" "Start FastAPI app locally"
	@printf "  %-18s %s\n" "worker" "Start background translation worker"
	@printf "  %-18s %s\n" "check-gpu" "Verify CUDA and GH200 visibility"
	@printf "  %-18s %s\n" "test" "Run unit/integration tests"
	@printf "  %-18s %s\n" "lint" "Run flake8"
	@printf "  %-18s %s\n" "format" "Format code with black and isort"
	@printf "  %-18s %s\n" "typecheck" "Run mypy static analysis"
	@printf "  %-18s %s\n" "docker-gpu" "Launch GPU stack (docker compose -d)"
	@printf "  %-18s %s\n" "docker-test" "Run test suite inside GPU container"
	@printf "  %-18s %s\n" "docker-logs" "Tail application logs from compose stack"
	@printf "  %-18s %s\n" "docker-shell" "Open shell inside the app container"
	@printf "  %-18s %s\n" "docker-down" "Stop docker compose services"
	@printf "  %-18s %s\n" "clean" "Remove build artifacts"
	@printf "  %-18s %s\n" "dist-clean" "Remove venv and generated databases"

$(INSTALL_STAMP): requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(VENVBIN)/python -m pip install --upgrade pip wheel setuptools
	$(VENVBIN)/python -m pip install -r requirements.txt
	@if [ -n "$(TORCH_INDEX_URL)" ]; then \
		echo "Installing CUDA-enabled PyTorch from $(TORCH_INDEX_URL)"; \
		$(VENVBIN)/python -m pip install --no-cache-dir --index-url $(TORCH_INDEX_URL) \
			torch==$(TORCH_VERSION) \
			torchvision==$(TORCHVISION_VERSION) \
			torchaudio==$(TORCHAUDIO_VERSION); \
	fi
	mkdir -p logs uploads outputs data
	touch $(INSTALL_STAMP)

setup: $(INSTALL_STAMP)

env:
	@if [ ! -f $(ENV_FILE) ] && [ -f .env.example ]; then \
		cp .env.example $(ENV_FILE); \
		echo "Created $(ENV_FILE) from template"; \
	fi

run: setup env
	$(PYTHON_BIN) main.py

worker: setup env
	$(PYTHON_BIN) -m src.workers.translation_worker

check-gpu: setup
	if command -v nvidia-smi >/dev/null 2>&1; then nvidia-smi; else echo "nvidia-smi not found"; fi
	$(PYTHON_BIN) check_gpu.py

test: setup
	CI=${CI} $(PYTHON_BIN) run_tests.py

lint: setup
	$(VENVBIN)/flake8 src tests

format: setup
	$(PYTHON_BIN) -m black src tests
	$(PYTHON_BIN) -m isort src tests

typecheck: setup
	$(VENVBIN)/mypy src

docker-gpu:
	docker compose -f docker-compose.gpu.yml up --build -d

docker-test:
	docker compose -f docker-compose.gpu.yml run --rm pdf-translator test

docker-logs:
	docker compose -f docker-compose.gpu.yml logs -f

docker-shell:
	docker compose -f docker-compose.gpu.yml exec pdf-translator bash

docker-down:
	docker compose -f docker-compose.gpu.yml down

redis-up:
	docker compose up -d redis

redis-down:
	docker compose stop redis

clean:
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
	find . -name "*.pyc" -delete
	rm -rf .mypy_cache .pytest_cache
	@if [ -d logs ]; then rm -f logs/*.log; fi

dist-clean: clean
	rm -rf $(VENV) jobs.db test.db outputs uploads $(INSTALL_STAMP)
	@if [ -d data ]; then rm -f data/*.db; fi
