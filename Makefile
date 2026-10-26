# ===========================================================================
# CONTRATO DE EJECUCION  --  NO RENOMBRES NI ELIMINES ESTOS TARGETS
# ===========================================================================

.PHONY: setup up run stream test down clean verificar

setup:
	python -m pip install --upgrade pip
	pip install -r requirements.txt

up:
	docker compose up -d

run:
	python src/batch/processor.py

stream:
	python src/streaming/consumer.py

test:
	pytest -v

down:
	docker compose down

clean:
	rm -rf out logs
	docker compose down -v --remove-orphans || true

verificar:
	python3 tools/verificar_entrega.py
