FROM python:3.13.4-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8765 \
    STOCK_RANKER_PROJECT_ROOT=/app \
    STOCK_RANKER_DATA_ROOT=/var/lib/stock-ranking/data \
    STOCK_RANKER_RESEARCH_ROOT=/var/lib/stock-ranking/research

WORKDIR /app
COPY requirements.lock pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir -r requirements.lock && \
    python -m pip install --no-cache-dir --no-deps . && \
    useradd --create-home --uid 10001 appuser

COPY marketdata ./marketdata
COPY research/registry ./research/registry
COPY release ./release
COPY data/analysis/complete_universe_20260918_run_05 ./data/analysis/complete_universe_20260918_run_05
COPY data/analysis/completed_universe_frozen_audit_20260920_run_01 ./data/analysis/completed_universe_frozen_audit_20260920_run_01
COPY data/analysis/universe_reconciliation_20260920_run_01 ./data/analysis/universe_reconciliation_20260920_run_01
COPY data/analysis/release_website_audit_20260920_run_01 ./data/analysis/release_website_audit_20260920_run_01

USER appuser
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=20s --start-period=45s --retries=3 \
  CMD python -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8765/api/health',timeout=15)); assert d['ready']" || exit 1

CMD ["sh", "-c", "python marketdata/runners/verify_release.py && exec python -m stock_ranker.webapp --host 0.0.0.0"]
