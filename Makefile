.PHONY: install test run-gui lint clean

install:
	pip install -r requirements.txt

test:
	python3 -m unittest test_processor.py

run-gui:
	python3 main.py

lint:
	flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics

clean:
	rm -rf md-created/*
	find . -type d -name "__pycache__" -exec rm -rf {} +
