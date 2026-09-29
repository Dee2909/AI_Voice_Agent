.PHONY: setup test run lint db-upgrade

setup:
	cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt

test:
	cd backend && source venv/bin/activate && pytest

run:
	cd backend && source venv/bin/activate && uvicorn app.main:app --reload

db-upgrade:
	cd backend && source venv/bin/activate && alembic upgrade head
