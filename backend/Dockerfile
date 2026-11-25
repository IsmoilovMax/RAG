# CPU-only backend image (no CUDA libraries are installed).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/models/hf \
    DATA_DIR=/data

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install the CPU build of PyTorch first so nothing pulls in the CUDA variant.
COPY requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install -r requirements.txt

# Bake the embedding model into the image so containers start offline and fast.
ARG EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
ARG PRELOAD_EMBEDDING_MODEL=true
RUN if [ "$PRELOAD_EMBEDDING_MODEL" = "true" ]; then \
      python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}', device='cpu')"; \
    fi

COPY app ./app
COPY scripts ./scripts

RUN useradd --uid 1000 --create-home appuser \
    && mkdir -p /data /models \
    && chown -R appuser:appuser /data /models /app
USER appuser

EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

# A single worker: the embedding model and ChromaDB client live in-process and
# are shared by all requests (async I/O + thread pools provide concurrency).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
