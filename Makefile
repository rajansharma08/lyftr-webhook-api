.PHONY: up down logs test clean

up:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f api

test:
	@echo "Running tests..."
	cd tests && python -m pytest -v

clean:
	docker compose down -v
	rm -rf app/__pycache__ tests/__pycache__