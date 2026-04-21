# RAG Runbook Assistant

An AI-powered IT operations assistant that answers engineering questions from a knowledge base of internal runbooks using **Retrieval-Augmented Generation (RAG)**. Built with ChromaDB, sentence-transformers, and the Claude API.


---

## What It Does

Engineers on-call frequently need to answer questions like *"how do I handle a high CPU alert?"* or *"what's the escalation path for a P1?"*. This assistant indexes a library of internal runbooks, retrieves the most relevant excerpts for any question, and uses Claude to generate a grounded, cited answer.

**Key properties:**

- **Grounded** — answers come from indexed runbooks, not model hallucination
- **Cited** — every answer lists which runbook(s) it used
- **Local-first** — embeddings and vector DB run fully on-device; only generation calls the API
- **Transparent** — debug panel shows the retrieved chunks and their relevance scores

---

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│  Runbooks   │──┬──▶│   Chunker    │─────▶│  ChromaDB   │
│   (.md)     │  │   │ (header-aware)│      │ + MiniLM-L6 │
└─────────────┘  │   └──────────────┘      └──────┬──────┘
                 │                                 │
                 │   ingest.py (one-time build)    │
                 │                                 ▼
                 │                          ┌─────────────┐
                 │   Web UI ──────────────▶│    Query    │
                 │                          │  Retrieval  │
                 │                          └──────┬──────┘
                 │                                 │
                 │                                 ▼
                 │                          ┌─────────────┐
                 └─────────────────────────▶│  Claude API │
                                            │  (Haiku 4.5)│
                                            └──────┬──────┘
                                                   │
                                                   ▼
                                            Cited Answer
```

### Components

| File | Purpose |
|------|---------|
| `app.py` | Flask web server and JSON API |
| `ingest.py` | One-time script to build the vector index |
| `src/rag_engine.py` | Core RAG pipeline: retrieve → prompt → generate |
| `src/vector_store.py` | ChromaDB wrapper with MiniLM embeddings |
| `src/chunker.py` | Header-aware markdown chunker |
| `templates/` + `static/` | Web UI |
| `runbooks/` | 10 sample IT operations runbooks |

---

## Setup

### 1. Install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Set your API key

```bash
cp .env.example .env
# Edit .env and paste your Anthropic API key
export $(cat .env | xargs)
```

### 3. Build the vector index

```bash
python ingest.py
```

You should see each runbook chunked and added. First run will download the MiniLM embedding model (~90 MB).

### 4. Run the web UI

```bash
python app.py
```

Open `http://localhost:5002`.

---

## Sample Queries

The indexed runbooks cover common ops scenarios. Try:

- *"How do I respond to a high CPU alert?"*
- *"What's the escalation path for a P1 incident?"*
- *"How do I rotate a leaked API key?"*
- *"My Kubernetes pod is in CrashLoopBackOff — what do I check?"*
- *"What's the procedure for rolling back a deployment?"*

Each answer will cite the runbook(s) it drew from.

---

## How the RAG Pipeline Works

1. **Ingestion** — runbooks are split into semantic chunks at `##` header boundaries, with overlap for chunks that span sections
2. **Embedding** — each chunk is embedded with `all-MiniLM-L6-v2` (384-dim, fast on CPU)
3. **Storage** — chunks and metadata are persisted in ChromaDB
4. **Query** — the user's question is embedded and compared against all stored chunks via cosine similarity
5. **Retrieval** — the top 4 most relevant chunks are pulled
6. **Generation** — chunks are inserted into a tightly-scoped system prompt that instructs Claude to answer **only** from the provided context and cite sources

## Design Choices

**Why ChromaDB over FAISS/Pinecone?** Zero setup, persistent by default, works offline. FAISS is faster at scale; Pinecone is the production choice — but for a portfolio demo, ChromaDB keeps the project self-contained.

**Why MiniLM over a larger embedding model?** MiniLM-L6 is ~90 MB, runs on CPU, and is strong enough for technical documentation. Upgrading to `bge-large` or Voyage is a one-line change in `vector_store.py`.

**Why Claude Haiku 4.5 for generation?** RAG works best when the model trusts the retrieved context rather than inventing. Haiku is fast, cost-effective, and strong at grounded summarization tasks.

**Why header-aware chunking?** Runbooks are structured — cutting across a `## Remediation` section mid-step destroys meaning. Chunking on `##` boundaries preserves procedural integrity.

---

## Extending the Assistant

- **Add your own runbooks:** drop markdown files into `runbooks/` and run `python ingest.py --reset`
- **Swap the embedding model:** change `model_name` in `src/vector_store.py`
- **Tune retrieval:** adjust `top_k` in `rag_engine.py` (default 4)
- **Swap the LLM:** change `self.model` in `rag_engine.py` (e.g. to `claude-opus-4-7` for harder reasoning)

---

## Tech Stack

| Layer | Tool |
|-------|------|
| Web framework | Flask |
| Vector DB | ChromaDB (persistent) |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) |
| Generation | Claude API (`claude-haiku-4-5`) |
| Frontend | Vanilla HTML/CSS/JS (no framework) |

Built with the [Anthropic Python SDK](https://docs.claude.com).

---

## Cost Analysis

Embedding and retrieval are **fully local** — no API cost at query time for those steps. Cost comes from generation only.

| Model | Input (per 1K tokens) | Output (per 1K tokens) |
|-------|-----------------------|------------------------|
| Claude Haiku 4.5 | $0.00080 | $0.00400 |

**Typical query cost:** ~800 input tokens (4 retrieved chunks + question) + ~300 output tokens ≈ **~$0.0018/query**

| Volume | Est. Monthly Cost |
|--------|-------------------|
| 10 queries/day | ~$0.54 |
| 50 queries/day | ~$2.70 |
| 200 queries/day | ~$10.80 |

Embedding model (`all-MiniLM-L6-v2`) runs locally — **$0.00** at any volume. Switching to a cloud embedding API (Voyage, OpenAI) would add ~$0.0001/query additional cost.
