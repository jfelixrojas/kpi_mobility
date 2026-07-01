.PHONY: run-visualization run-news-evaluation download-osm-departments run-incidentes-analysis run-corridor-weight-experiments run-incidentes-figures run-incidentes-dashboard

PYTHON ?= python3
STREAMLIT_PORT ?= auto
STREAMLIT_HOST ?= 127.0.0.1

run-visualization:
	@PORT="$(STREAMLIT_PORT)"; \
	if [ "$$PORT" = "auto" ]; then \
		PORT=8501; \
		while $(PYTHON) -c 'import socket, sys; sock = socket.socket(); code = sock.connect_ex((sys.argv[1], int(sys.argv[2]))); sock.close(); sys.exit(0 if code == 0 else 1)' "$(STREAMLIT_HOST)" "$$PORT"; do \
			PORT=$$((PORT + 1)); \
		done; \
	fi; \
	echo "Streamlit: http://$(STREAMLIT_HOST):$$PORT"; \
	$(PYTHON) -m streamlit run Codigos/streamlit_osm_news_map.py --server.port $$PORT --server.address $(STREAMLIT_HOST)

run-news-evaluation:
	$(PYTHON) Codigos/news_source_fitness_evaluation.py

download-osm-departments:
	$(PYTHON) Codigos/osm_overpass_departments.py

run-incidentes-analysis:
	$(PYTHON) Codigos/incidentes_analysis_pipeline.py
	$(PYTHON) Codigos/corridor_weight_experiments.py

run-corridor-weight-experiments:
	$(PYTHON) Codigos/corridor_weight_experiments.py

run-incidentes-figures:
	$(PYTHON) Codigos/generate_incidentes_executive_figures.py


run-incidentes-dashboard:
	@PORT="$(STREAMLIT_PORT)"; \
	if [ "$$PORT" = "auto" ]; then \
		PORT=8501; \
		while $(PYTHON) -c 'import socket, sys; sock = socket.socket(); code = sock.connect_ex((sys.argv[1], int(sys.argv[2]))); sock.close(); sys.exit(0 if code == 0 else 1)' "$(STREAMLIT_HOST)" "$$PORT"; do \
			PORT=$$((PORT + 1)); \
		done; \
	fi; \
	echo "Streamlit incidentes: http://$(STREAMLIT_HOST):$$PORT"; \
	$(PYTHON) -m streamlit run Codigos/streamlit_incidentes_dashboard.py --server.port $$PORT --server.address $(STREAMLIT_HOST)
