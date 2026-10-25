.PHONY: install data train evaluate seed api web test benchmark lint build docker

install:
	python -m pip install -e ".[dev]"
	cd frontend && npm ci

data:
	python scripts/generate_data.py

train:
	python scripts/train.py

evaluate:
	python scripts/evaluate.py

seed:
	python scripts/seed_db.py

api:
	uvicorn apps.api.main:app --reload --port 8000

web:
	cd frontend && npm run dev

test:
	python -m pytest --cov=rasa --cov-fail-under=50

benchmark:
	python scripts/benchmark_api.py --requests 10

lint:
	python -m ruff check .
	cd frontend && npm run lint

build:
	cd frontend && npm run build

docker:
	docker compose up --build
