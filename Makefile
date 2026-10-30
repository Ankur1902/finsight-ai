.PHONY: demo test gate redteam
demo:        ## build and run the full stack
	docker compose up --build
test:
	python -m pytest -q
gate:
	python -m src.eval.ci_gate
redteam:
	python -m src.eval.redteam --write
