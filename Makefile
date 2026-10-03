.PHONY: setup test run prototype lint typecheck db-upgrade docker-up docker-down

setup:
	cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt

test:
	cd backend && source venv/bin/activate && pytest tests/ -v

lint:
	cd backend && source venv/bin/activate && ruff check .

typecheck:
	cd backend && source venv/bin/activate && mypy app/

run:
	cd backend && source venv/bin/activate && uvicorn app.main:api_app --host 0.0.0.0 --port 8000 --reload

prototype:
	./run_prototype.sh

db-upgrade:
	cd backend && source venv/bin/activate && alembic upgrade head

docker-up:
	docker compose up -d

docker-down:
	docker compose down
