# Team 10 demo UI. Build from the repository root:  docker build -f ui/Dockerfile -t team10-ui .
# Only what ui/server.py, run_review.py, the harness and retrieval need is copied; never .env or reports.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UI_HOST=0.0.0.0 \
    UI_PORT=8000

RUN pip install --no-cache-dir "openai>=1.0" "pydantic>=2.0" "PyYAML>=6.0" \
    && useradd --system --uid 10001 --no-create-home app \
    && mkdir -p /app/reports /app/data "/app/ITSG Files" \
    && chown app /app/reports

WORKDIR /app
COPY run_review.py /app/
COPY checker/ /app/checker/
COPY harness/ /app/harness/
COPY retrieval/ask.py retrieval/search.py /app/retrieval/
COPY chunks/ /app/chunks/
# privacy airlock (ask.py, the UI server and the Langfuse guard import it)
COPY privacy/__init__.py privacy/schleuse.py privacy/langfuse_guard.py privacy/leak_test.py privacy/test_independent.py /app/privacy/
COPY seal/seal_common.py /app/seal/seal_common.py
COPY data/testcases.json data/story_cases.json data/case_correct.json /app/data/
COPY ["ITSG Files/TEEL0-Test1-DBVO", "/app/ITSG Files/TEEL0-Test1-DBVO"]
COPY figures/ /app/figures/
COPY ui/index.html /app/ui/index.html
COPY ui/css/ /app/ui/css/
COPY ui/js/ /app/ui/js/
COPY ui/server.py /app/ui/server.py

# leak-test result made at build time (the reports volume hides anything written there); the UI also runs it on demand
RUN python privacy/leak_test.py --json /app/privacy/leaktest-build.json > /dev/null

USER app
VOLUME /app/reports
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["python", "ui/server.py"]
