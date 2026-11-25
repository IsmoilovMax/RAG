# DocuMind — CPU-only RAG document assistant

DocuMind lets you upload documents and ask questions about them. It retrieves the most relevant passages from your files and has a **local LLM** answer **only from those passages**, with clickable citations, page numbers and the exact snippets used. Everything runs on CPU: there is no NVIDIA GPU, CUDA or cloud API involved.

| | |
|---|---|
| **Backend** | Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 (SQLite for development, PostgreSQL for production) |
| **RAG** | Sentence-Transformers `BAAI/bge-small-en-v1.5` (CPU), ChromaDB, LangChain text splitters |
| **Parsing** | PyMuPDF (PDF), python-docx (DOCX), openpyxl (XLSX), python-pptx (PPTX), TXT/MD/CSV |
| **LLM** | Ollama with `qwen2.5:3b` by default (quantised GGUF, CPU inference), configurable |
| **Frontend** | React 19, TypeScript, Vite, Tailwind CSS v4, shadcn/ui (Radix), Lucide icons, TanStack Query |
| **Deploy** | Docker Compose: nginx + UI, API, PostgreSQL, Ollama |

---

## Contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [How answers stay grounded](#how-answers-stay-grounded)
4. [Quick start with Docker](#quick-start-with-docker)
5. [Local development](#local-development)
6. [Configuration](#configuration)
7. [CPU-only deployment on a Linux VPS](#cpu-only-deployment-on-a-linux-vps)
8. [API reference](#api-reference)
9. [Testing](#testing)
10. [Sample documents and questions](#sample-documents-and-questions)
11. [Troubleshooting](#troubleshooting)
12. [Design notes and limitations](#design-notes-and-limitations)

---

## Features

**Document management**
- Upload PDF, DOCX, TXT, MD, CSV, XLSX and PPTX files, several at a time, by drag and drop or a file picker.
- Every upload is checked for:
  - an allowed extension;
  - content matching its type (magic bytes; Office files must contain the right internal parts);
  - the size limit, enforced while streaming;
  - a safe file name.
- **Duplicate prevention** by SHA-256 content hash, so the same file under another name is detected too.
- Processing runs in a **background worker pool**, with live status (queued, processing with %, ready, failed with the reason). Interrupted jobs resume when the server restarts.
- Tracked metadata: size, type, pages/slides/sheets, characters, chunk count, the chunk settings used, the embedding model and processing time.
- Inspect the indexed chunks of any document, download the original, re-process one document, re-index everything, or delete a document (its vectors and file are removed as well).

**RAG pipeline**
ingestion → text extraction → cleaning → structure-aware chunking → batch embedding → vector storage → similarity search → threshold filtering → context assembly → grounded generation.

**AI chat**
- A ChatGPT-style interface with **streaming answers** over Server-Sent Events, and a stop button.
- For each answer:
  - clickable **citation chips**;
  - a source list showing file, page, slide or sheet, similarity score, and whether the passage was cited or only retrieved;
  - the retrieved snippet.
- Persistent conversation history: rename, delete, or clear a chat. Follow-up questions are understood.
- Optionally limit a question to selected documents.
- A clear "documents do not contain sufficient information" state, including the best similarity score against the threshold.

**Dashboard, settings, UX**
- **Dashboard**: document and chunk counts, questions answered, average latency, a grounding breakdown, library status, recent documents, and live health of the database, vector store, embedding model and LLM.
- **Settings**: choose from your installed Ollama models, and tune temperature, top-k, similarity threshold, relative cutoff, context budget, conversation memory, and chunk size and overlap. You are warned when documents were indexed with outdated chunk settings, with one-click re-indexing.
- Light, dark and system themes; a responsive layout down to phone width; skeleton loaders; empty and error states; toast notifications.

---

## Architecture

```
┌──────────────┐  /api (REST + SSE)  ┌──────────────────────────────────────────────┐
│ React + Vite │ ──────────────────▶ │ FastAPI                                      │
│ shadcn/ui    │ ◀────────────────── │  api/routes ── documents · chat · settings   │
└──────────────┘     nginx proxy     │                 · health · stats             │
                                     │  services ──┬─ DocumentService (uploads)     │
                                     │             ├─ IngestionService (thread pool)│
                                     │             │    parse → clean → chunk →     │
                                     │             │    embed (batched) → store     │
                                     │             ├─ ChatService (history, SSE)    │
                                     │             └─ RagService                    │
                                     │                  Retriever → prompts → LLM   │
                                     └──┬──────────────┬─────────────┬──────────────┘
                                        │              │             │
                          SQLAlchemy    │   ChromaDB   │  Ollama HTTP│
                     (SQLite/Postgres)  ▼  (cosine)    ▼  (CPU GGUF) ▼
                 documents, chats,     vectors +      qwen2.5:3b (configurable)
                 settings              metadata       bge-small-en-v1.5 runs in-process
```

```
backend/
  app/
    main.py                 # app factory, lifespan, middleware
    container.py            # builds every long-lived service exactly once
    core/                   # config (env), structured logging, API-key security, errors
    db/                     # SQLAlchemy models + engine/session (SQLite or PostgreSQL)
    schemas/                # Pydantic request/response models
    api/routes/             # thin HTTP layer: documents, chat, settings, health, stats
    services/
      parsing/              # one parser per format + upload content validation
      text_cleaning.py      # unicode/whitespace normalisation, de-hyphenation, line merging
      chunking.py           # section-aware recursive splitter (row-aware for tables)
      embeddings.py         # SentenceTransformer singleton, CPU, batched, normalised
      vector_store.py       # ChromaDB wrapper (cosine), batched upserts, filters
      retrieval.py          # threshold + relative cutoff + dedup + context budget
      prompts.py            # grounding prompts, citation helpers, answer tidying
      rag.py                # retrieve → prompt → generate; answer types
      llm.py                # async Ollama client (streaming)
      ingestion.py          # background pipeline + resume on restart
      document_service.py   # secure uploads, de-duplication, deletion
      chat_service.py       # conversations, SSE streaming, persistence
      settings_service.py   # runtime settings (env defaults + UI overrides)
  scripts/generate_samples.py
  tests/
frontend/
  src/
    pages/                  # dashboard, documents, chat, settings
    components/ui/          # shadcn/ui primitives
    components/{chat,documents,layout}/
    hooks/queries.ts        # TanStack Query hooks (polling while ingesting)
    lib/                    # API client, SSE parser, types, utils
samples/                    # sample documents + QUESTIONS.md
docker-compose.yml
```

**Why no full LangChain or LlamaIndex stack?** Only LangChain's well-tested `RecursiveCharacterTextSplitter` is used. Chroma, Sentence-Transformers and Ollama are called directly, which keeps the hot path small and explicit and avoids hidden model loading. It also gives precise control over thresholds, metadata and prompts, all of which matter on CPU and with small models.

**Performance on CPU**
- **No duplicate models**: the embedding model is loaded **once** (thread-safe and lazy, warmed at startup), and encode calls are serialised so concurrent uploads don't multiply peak RAM.
- **Batching**: embeddings are generated in batches (`EMBEDDING_BATCH_SIZE`), and vectors are upserted to Chroma in batches.
- **Ingestion**: uploads stream to disk in 1 MB chunks and are hashed on the fly, and ingestion is incremental, so each new document is indexed on its own.
- **Async**: the API is asynchronous, with CPU-bound work (retrieval, parsing) moved off the event loop into threads.
- **LLM settings**: Ollama keeps the quantised model loaded between questions (`OLLAMA_KEEP_ALIVE`), and the context window (`OLLAMA_NUM_CTX`) and thread count are configurable.

---

## How answers stay grounded

1. **Similarity threshold.** Chunks whose cosine similarity is below `SIMILARITY_THRESHOLD` (default **0.55**) are discarded. If nothing passes, the backend answers *"The uploaded documents do not contain sufficient information to answer this question."* **without calling the LLM at all**. This makes it impossible to hallucinate an answer from nothing.
2. **Relative cutoff.** Chunks scoring more than `RELATIVE_SCORE_CUTOFF` below the best match are dropped, so weakly related text doesn't dilute the context. Near-duplicate chunks are removed, and the context is capped at `MAX_CONTEXT_CHARS`.
3. **Grounding prompt.** The model is told to use only the numbered passages, never to invent facts, to cite passages as `[n]`, and to reply with the exact refusal sentence when the passages don't contain the answer.
4. **Facts vs. AI explanation.** Any reasoning that is not stated in the passages must go in a final paragraph starting with `Explanation:`. The UI shows it in a separate callout labelled *"AI explanation — not stated directly in your documents"*. Retrieved facts appear as cited text, with the exact snippets in the source list.
5. **Answer post-processing.** Citations to non-existent passages are removed. A redundant refusal appended to a supported answer is dropped. Each source is marked as **Cited** or only **Retrieved**.
6. **Answer types** are stored with every message and shown on the dashboard:
   - `grounded`: answered from passages;
   - `insufficient`: context was found, but the model said it doesn't answer the question;
   - `no_context`: nothing passed the threshold;
   - `error`: generation failed.

The default threshold was calibrated on the sample set using `bge-small-en-v1.5`:

| Question set | Similarity of the top passage |
|---|---|
| Answerable questions | 0.57 – 0.89 |
| Off-topic questions | ≤ 0.51 |

Re-calibrate the threshold on the Settings page if your documents differ a lot.

**Small-model prompt engineering.** The prompts were tuned on `qwen2.5:3b`:
- a short system prompt, with the instructions placed right after the question;
- no content-bearing examples, because small models copy them into answers;
- for follow-ups, only earlier *questions* are given as reference. Replaying earlier answers made the 3B model refuse follow-ups that the passages actually answer.

---

## Quick start with Docker

Requirements: Docker Engine 24+ with the Compose plugin. About 6 GB of free disk is needed for the images, the model and the data.

```bash
git clone <this repo> documind && cd documind
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD (required) and, for anything internet-facing, API_KEY.
docker compose up -d --build
docker compose logs -f ollama-pull   # first run downloads qwen2.5:3b (~1.9 GB)
```

Open **http://localhost:8080** (or `http://<server-ip>:8080`). Then:
1. Go to **Documents** and drop in files, for example everything in `samples/`.
2. Wait until each file shows **Ready**.
3. Go to **AI Chat** and ask a question, for example *"How many days of annual leave do employees get?"*.

Compose services:

| Service | Purpose |
|---|---|
| `frontend` | nginx serving the built UI. It proxies `/api` to the backend with SSE buffering disabled. |
| `backend` | FastAPI on CPU. The embedding model is baked into the image, and data lives in the `backend-data` volume (uploads + Chroma). |
| `postgres` | PostgreSQL 16 for metadata, chats and settings. |
| `ollama` / `ollama-pull` | Ollama server, plus a one-shot job that pulls `OLLAMA_MODEL`. |

Useful commands:

```bash
docker compose ps                                  # health of all services
docker compose exec ollama ollama pull llama3.2:3b # add another model (then pick it in Settings)
docker compose logs -f backend                     # JSON structured logs
docker compose down                                # stop (volumes keep your data)
```

---

## Local development

### 1. Ollama (CPU)

Install it from https://ollama.com/download, or run it in Docker:

```bash
docker run -d --name ollama -p 11434:11434 -v ollama:/root/.ollama ollama/ollama
docker exec ollama ollama pull qwen2.5:3b
```

A native install can just use `ollama pull qwen2.5:3b`.

### 2. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt       # installs the CPU-only PyTorch wheel
cp ../.env.example .env                   # optional; defaults work for local use
uvicorn app.main:app --reload --port 8000
```

- With no `DATABASE_URL`, a SQLite DB is created at `backend/data/app.db`, and uploads and the Chroma index go to `backend/data/`.
- The embedding model (~130 MB) downloads from Hugging Face on first start and is cached.
- Interactive API docs are at http://localhost:8000/api/docs.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173 (proxies /api to :8000)
npm run build          # production build in dist/
npm test               # unit tests (vitest)
```

Set `VITE_PROXY_TARGET` to point the dev proxy at another backend. Set `VITE_API_BASE_URL` at build time if the UI is served from a different origin than the API, and add that origin to `CORS_ORIGINS`.

---

## Configuration

All settings are environment variables; see [`.env.example`](.env.example) for the full annotated list. Values are read from `.env` in the repo root or `backend/`. The **RAG defaults can also be changed at runtime** on the Settings page. Those overrides are stored in the database, and **Reset to defaults** restores the env values.

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `OLLAMA_MODEL` | `qwen2.5:3b` | Default LLM (any model in `ollama list`) |
| `OLLAMA_NUM_CTX` | `4096` | Context window (tokens) |
| `OLLAMA_NUM_THREAD` | auto | CPU threads for generation |
| `OLLAMA_KEEP_ALIVE` | `30m` | Keep the model in RAM between requests |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Sentence-Transformers model (CPU) |
| `EMBEDDING_BATCH_SIZE` | `32` | Chunks per embedding batch |
| `TORCH_NUM_THREADS` | auto | CPU threads for embeddings |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1000` / `150` | Characters per chunk / overlap |
| `RETRIEVAL_TOP_K` | `5` | Maximum passages given to the LLM |
| `SIMILARITY_THRESHOLD` | `0.55` | Minimum cosine similarity |
| `RELATIVE_SCORE_CUTOFF` | `0.12` | Drop passages this far below the best |
| `MAX_CONTEXT_CHARS` | `6000` | Context budget |
| `HISTORY_TURNS` | `3` | Earlier questions used for follow-ups |
| `LLM_TEMPERATURE` | `0.1` | Generation temperature |
| `DATABASE_URL` | SQLite in `DATA_DIR` | e.g. `postgresql://user:pass@host:5432/db` |
| `DATA_DIR` | `backend/data` | Uploads, Chroma index, SQLite DB |
| `MAX_UPLOAD_MB` / `MAX_FILES_PER_UPLOAD` | `50` / `20` | Upload limits |
| `API_KEY` | empty (open) | Require `X-API-Key` or `Authorization: Bearer` on all non-health endpoints |
| `CORS_ORIGINS` | Vite dev URLs | Comma-separated allowed origins |
| `LOG_LEVEL` / `LOG_JSON` | `INFO` / `false` | Structured JSON logs when `true` |
| `INGESTION_WORKERS` | `1` | Parallel ingestion jobs (1 keeps RAM low) |

**Changing the LLM.** Pull the model (`ollama pull llama3.2:3b`), then either set `OLLAMA_MODEL` or pick it on the Settings page. No restart is needed. Good CPU choices are `qwen2.5:3b`, `llama3.2:3b`, `phi3.5` and, with 16 GB+ RAM, `qwen2.5:7b`. All of them are quantised GGUF builds (Q4_K_M) served by Ollama.

**Changing chunking.** Chunk settings apply to newly processed documents. The Settings page shows how many documents are stale, and **Re-index** rebuilds them.

---

## CPU-only deployment on a Linux VPS

**Sizing (qwen2.5:3b)**

| | vCPU | RAM | Disk | Speed |
|---|---|---|---|---|
| Minimum | 4 | 8 GB | 20 GB SSD | ~3–8 tokens/s |
| Recommended | 8 | 16 GB | — | Typical answers take 3–15 s |

A smaller footprint is possible with `qwen2.5:1.5b` (4 GB RAM).

```bash
# 1. Install Docker (Ubuntu/Debian)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker

# 2. Optional but recommended on small VPSs: add swap
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 3. Deploy
git clone <this repo> /opt/documind && cd /opt/documind
cp .env.example .env
sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 24)/" .env
sed -i "s/^API_KEY=.*/API_KEY=$(openssl rand -hex 32)/" .env
docker compose up -d --build
```

Nothing in the stack requests a GPU: the images ship the CPU PyTorch wheel, and Ollama falls back to CPU automatically.

**Production checklist**
- Put a TLS reverse proxy in front of port 8080 (Caddy: `documind.example.com { reverse_proxy localhost:8080 }`). For nginx, keep `proxy_buffering off` for `/api/`.
- Set `API_KEY` and enter it once in the UI (**Settings → API key**; it is stored only in that browser). Health probes (`/api/health`, `/api/health/ready`) stay open for monitoring.
- Don't expose ports 11434 (Ollama) or 5432 (Postgres): the compose file keeps them on the internal network.
- Back up the `postgres` and `backend-data` volumes (uploads + vector index).
- Tune `OLLAMA_NUM_THREAD` and `TORCH_NUM_THREADS` to your vCPU count, and `BACKEND_MEMORY_LIMIT` to your RAM.
- Readiness: `curl localhost:8080/api/health/ready` reports each component.

**Running without Docker (systemd).** Install Ollama natively, create the venv as in [Local development](#local-development), and run:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Then serve `frontend/dist` with nginx using [`frontend/nginx.conf`](frontend/nginx.conf), changing `proxy_pass` to `http://127.0.0.1:8000`.

---

## API reference

Interactive OpenAPI docs are at `/api/docs`. All endpoints except health require the API key when `API_KEY` is set.

| Method & path | Description |
|---|---|
| `GET /api/health` | Liveness |
| `GET /api/health/ready` | Readiness of DB, vector store, embeddings, LLM (+ installed models) |
| `GET /api/stats` | Dashboard statistics |
| `POST /api/documents` | Upload one or more files (`multipart/form-data`, field `files`). Returns `accepted` / `duplicate` / `rejected` per file |
| `GET /api/documents?status=&q=` | List / filter / search documents |
| `GET /api/documents/{id}` | Document metadata and status |
| `GET /api/documents/{id}/chunks` | Indexed chunks |
| `GET /api/documents/{id}/file` | Download the original |
| `POST /api/documents/{id}/reprocess` | Re-run ingestion for one document |
| `POST /api/documents/reindex` | Re-index all documents |
| `DELETE /api/documents/{id}` | Delete document, vectors and file |
| `POST /api/chat/stream` | Ask with streaming (SSE). Events: `meta`, `sources`, `token`, `done`, `error` |
| `POST /api/chat/ask` | Ask without streaming |
| `GET/POST /api/chat/conversations` | List / create conversations |
| `GET/PATCH/DELETE /api/chat/conversations/{id}` | Read / rename / delete |
| `DELETE /api/chat/conversations/{id}/messages` | Clear a chat |
| `GET/PUT /api/settings`, `POST /api/settings/reset` | Runtime settings |
| `GET /api/settings/models` | Installed Ollama models |

Example request body for the chat endpoints:

```json
{ "question": "string", "conversation_id": "optional", "document_ids": ["optional"] }
```

Example:

```bash
curl -s -X POST localhost:8000/api/documents -F files=@samples/employee_handbook.pdf
curl -s -X POST localhost:8000/api/chat/ask -H 'Content-Type: application/json' \
     -d '{"question":"How many days of annual leave do employees get?"}' | jq .assistant_message.content
# "Every full-time employee receives 28 days of paid annual leave per calendar year [1]."
```

---

## Testing

```bash
cd backend
pytest -m "not integration"     # unit, API and real-embedding-model tests (~6 min on CPU)
pytest -m integration           # end-to-end answers against a running Ollama with qwen2.5:3b
pytest                          # everything (integration tests auto-skip if Ollama is down)
cd ../frontend && npm test      # SSE parser + answer rendering helpers
```

| Suite | Covers |
|---|---|
| `test_parsing.py` | Every format, with pages/slides/sheets/sections preserved. Also encoding fallback, CSV dialects, spoofed/corrupt/encrypted/empty files |
| `test_chunking.py` | Cleaning rules, size and overlap limits, section boundaries, row-safe table chunking, invalid parameters |
| `test_embeddings.py` | Real `bge-small-en-v1.5` on CPU: dimension, normalisation, batch consistency, semantic ordering, single load |
| `test_vector_store.py` | Cosine ranking, filters, upsert idempotency, deletion, large batches, persistence |
| `test_retrieval.py` | Threshold, relative cutoff, de-duplication, context budget. **Retrieval accuracy**: all 12 sample questions retrieve the correct source and fact; off-topic questions retrieve nothing |
| `test_rag.py` | Grounding prompts, citations, no-context short-circuit (the LLM is never called), insufficient detection, history handling, answer tidying |
| `test_ingestion.py` | Metadata, idempotent re-processing, failures, resume after restart, runtime chunk settings |
| `test_api.py` | Every endpoint, including uploads (multi, duplicate, rejected, oversize, sanitised names), SSE event sequence, errors, conversations, settings validation, stats and API-key auth |
| `test_integration_ollama.py` | Real answers from `qwen2.5:3b` contain the expected facts, follow-ups work, unanswerable questions are refused |

API tests use a deterministic hashing embedder and a fake LLM, so they are fast and offline. The model and integration suites exercise the real components.

---

## Sample documents and questions

`samples/` contains one file per supported format about a fictional company, *Northwind Robotics*. Because the facts are invented, a correct answer proves retrieval works rather than the model's prior knowledge. Regenerate them with `python backend/scripts/generate_samples.py`.

| File | Content |
|---|---|
| `employee_handbook.pdf` | 3 pages: company, leave policy, remote work |
| `atlas_x2_specification.docx` | Robot spec with headings and a model table |
| `q3_sales_report.xlsx` | Sheets "Regional Sales" and "Q4 Targets" |
| `onboarding_presentation.pptx` | 3 slides with speaker notes |
| `support_faq.txt` | Warranty, SLA, firmware FAQ |
| `inventory.csv` | Parts inventory |

See [`samples/QUESTIONS.md`](samples/QUESTIONS.md) for example questions with expected answers, for example:
- *"What was the Q3 revenue in the DACH region?"* → 3,150,000 EUR (from `q3_sales_report.xlsx`, Regional Sales)
- *"Where do new hires pick up their laptop on day 1?"* → Building C reception (slide 2)
- *"What is the capital of Australia?"* → the documents do not contain sufficient information

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Dashboard shows **LLM: Ollama unreachable** | Start Ollama, or check `OLLAMA_BASE_URL`. In Docker it is `http://ollama:11434`. |
| **Model 'x' is not pulled** | `ollama pull x` (Docker: `docker compose exec ollama ollama pull x`) |
| Document **Failed: No extractable text** | A scanned or image-only PDF. OCR is not included; run OCR first, e.g. `ocrmypdf in.pdf out.pdf`. |
| Answers say "insufficient information" too often | Lower the similarity threshold a little (0.50) or raise top-k in Settings, and check the chunks in **Documents → View chunks**. |
| Irrelevant passages appear | Raise the threshold or lower the relative cutoff. |
| Slow answers | Use a smaller model (`qwen2.5:1.5b`), lower `OLLAMA_NUM_CTX`/`MAX_CONTEXT_CHARS`/top-k, and set `OLLAMA_NUM_THREAD` to your physical cores. The first answer after idle includes model load time. |
| 401 errors in the UI | Enter the server's `API_KEY` under **Settings → API key**. |
| Upload rejected with 413 behind a proxy | Raise `client_max_body_size` in your reverse proxy. |
| Windows: `vitest` reports "Cannot read properties of undefined (reading 'config')" | The drive letter in your shell's working directory has a different case from the real path (`f:` vs `F:`). `cd` using the upper-case drive letter. |

---

## Design notes and limitations

- **Single API process.** The embedding model and the embedded Chroma client live in-process, so run one Uvicorn worker. Concurrency comes from async I/O and thread pools. To scale horizontally, run Chroma in client/server mode and move ingestion to a queue.
- **Schema management.** Tables are created at startup (`create_all`). Add Alembic migrations before evolving the schema in production.
- **OCR** for scanned PDFs and image extraction are out of scope.
- The embedding model is English-focused. For multilingual documents, set `EMBEDDING_MODEL=BAAI/bge-m3` (larger and slower) and re-index.
- Small CPU models occasionally format citations imperfectly. The backend tidies common slips (misplaced or repeated citations, invalid passage numbers, redundant refusals) without altering content. Always verify important answers against the cited snippets.
