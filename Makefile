.PHONY: install run lint docker-build docker-up docker-down

PYTHON ?= python3
DOCKER_COMPOSE ?= docker compose -f infra/docker-compose.yml

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

run:
	$(PYTHON) bot/bot.py

lint:
	$(PYTHON) -m compileall bot

docker-build:
	docker build -f infra/Dockerfile -t gg-chatbot .

docker-up:
	$(DOCKER_COMPOSE) up --build

docker-down:
	$(DOCKER_COMPOSE) down -v
