# ITSG receipt office. Build from the repository root:  docker build -f seal/Dockerfile -t team10-seal .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    SEAL_HOST=0.0.0.0 \
    SEAL_PORT=8080 \
    SEAL_LEDGER=/data/ledger.jsonl

RUN useradd --system --uid 10001 --no-create-home seal \
    && mkdir /data /app \
    && chown seal /data

WORKDIR /app
COPY seal/ /app/

USER seal
VOLUME /data
EXPOSE 8080
CMD ["python", "server.py"]
