.PHONY: help up down logs migrate makemigrations shell test lint createsuperuser fmt

help:
	@echo "Common targets:"
	@echo "  make up                — docker compose up -d"
	@echo "  make down              — docker compose down"
	@echo "  make logs              — tail web logs"
	@echo "  make migrate           — apply migrations"
	@echo "  make makemigrations    — create new migrations"
	@echo "  make shell             — Django shell inside web container"
	@echo "  make createsuperuser   — create Django admin user"
	@echo "  make test              — run pytest in web container"
	@echo "  make lint              — ruff check"
	@echo "  make fmt               — ruff format"

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f web

migrate:
	docker compose exec web python manage.py migrate

makemigrations:
	docker compose exec web python manage.py makemigrations

shell:
	docker compose exec web python manage.py shell

createsuperuser:
	docker compose exec web python manage.py createsuperuser

test:
	docker compose exec web pytest

lint:
	ruff check .

fmt:
	ruff format .
