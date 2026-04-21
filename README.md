# RAG Runbook Assistant

An AI-powered IT operations assistant that answers engineering questions from a knowledge base of internal runbooks using Retrieval-Augmented Generation (RAG). Built with ChromaDB, sentence-transformers, and the Claude API.

> Index your runbooks once → ask questions in plain English → get grounded, cited answers. Deployed on a Linux VPS behind Cloudflare.

---

## Live Demo

🔗 **[runbooks.ado-runner.com](https://runbooks.ado-runner.com)**

---

## What It Does

Engineers on-call frequently need fast answers: *"How do I respond to a high CPU alert?"* or *"What's the escalation path for a P1?"* This assistant indexes a library of internal runbooks, retrieves the most relevant excerpts for any question, and uses Claude to generate a grounded, cited answer.

**Key properties:**

- **Grounded** — answers come from indexed runbooks, not model hallucination
- **Cited** — every answer lists which runbook(s) it drew from
- **Local-first** — embeddings and vector DB run fully on-device; only generation calls the API
- **Transparent** — debug panel shows retrieved chunks and their relevance scores

---

## Sample Output

### Query: "How do I respond to a high CPU alert?"

```
1. Immediately check which process is consuming CPU:
   `top` or `ps aux --sort=-%cpu | head -10`

2. If a runaway process is identified, investigate before killing:
   `ls -l /proc/<PID>/exe`

3. If safe to terminate:
   `kill -15 <PID>`   # graceful
   `kill -9 <PID>`    # force if unresponsive

4. Check system load trend:
   `uptime` — load average should be < number of CPU cores

5. Escalate to P1 if CPU stays above 95% for more than 5 minutes
   or if the offending process cannot be identified.

Sources: 01-high-cpu-alert.md, 02-incident-escalation.md
```

### Debug Panel (retrieved chunks)

```
01-high-cpu-alert.md     score: 0.847
02-incident-escalation.md    score: 0.721
07-oncall-handbook.md        score: 0.598
```

---

## Architecture

```
Runbooks (.md)
      │
      ▼
  ingest.py (one-time)
      │
  ┌───┴──────────────┐
  │   chunker.py      │  Header-aware markdown splitter
  │   (## boundaries) │  with paragraph-level overlap
  └───┬──────────────┘
      │
      ▼
  ChromaDB (persistent)
  + all-MiniLM-L6-v2 embeddings (local, CPU)
      │
      │   Query time
      │
  Web UI ──► /api/query
                │
          vector_store.py
          (cosine similarity, top-4 chunks)
                │
          rag_engine.py
          (chunks → Claude prompt)
                │
          Claude API (Haiku 4.5)
                │
          Cited answer + sources
```

```
Browser ──► Cloudflare (SSL/DDoS) ──► Nginx (reverse proxy) ──► Gunicorn:5002
                                                                       │
                                                               Claude API (Anthropic)
```

**Key design decisions:**
- Gunicorn binds to `127.0.0.1:5002` only — never exposed directly
- Nginx handles all public traffic; Cloudflare sits in front for SSL termination and DDoS protection
- ChromaDB persists to disk — index survives restarts, no re-ingestion needed
- Embeddings are fully local — zero API cost at retrieval time; cost only occurs at generation
- Header-aware chunking preserves runbook section integrity — no cutting procedures mid-step

---

## Tech Stack

| Layer | Technology |
|---|---|
| Vector DB | ChromaDB (persistent) |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`, local CPU) |
| AI generation | Anthropic Claude API (`claude-haiku-4-5`) |
| API server | Flask 3, Gunicorn |
| Frontend | Vanilla HTML/CSS/JS — no framework, no build step |
| Reverse proxy | Nginx |
| CDN / SSL | Cloudflare |
| Process management | systemd |
| OS / Hosting | Ubuntu 24.04 VPS |

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Web UI |
| `POST /api/query` | RAG query — returns answer, sources, retrieved chunks |
| `GET /api/stats` | Document and chunk counts |

---

## Setup

### 1. Clone & install dependencies

```bash
git clone https://github.com/ohdasdiego/rag-runbook-assistant.git
cd rag-runbook-assistant
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### 3. Index your runbooks

```bash
python ingest.py
# First run downloads the MiniLM model (~90 MB)
# Re-index after adding new runbooks:
python ingest.py --reset
```

### 4. Start the web UI

```bash
gunicorn app:app --bind 0.0.0.0:5002
# Dashboard at http://localhost:5002
```

### 5. Deploy as a systemd service

```bash
# Edit rag-runbook-assistant.service — replace YOUR_LINUX_USER with your username
sudo cp rag-runbook-assistant.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rag-runbook-assistant
sudo systemctl start rag-runbook-assistant
```

### 6. Nginx reverse proxy

```bash
# Edit nginx.conf — replace the server_name with your domain
sudo cp nginx.conf /etc/nginx/sites-available/rag-runbook-assistant
sudo ln -s /etc/nginx/sites-available/rag-runbook-assistant /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Point Cloudflare DNS to your server IP with the orange cloud (proxied) enabled.

---

## Adding Your Own Runbooks

Drop any markdown file into `runbooks/` and re-index:

```bash
python ingest.py --reset
```

The chunker splits on `##` header boundaries, so well-structured runbooks with clear sections get the best retrieval quality. Plain text files work too.

---

## Cost Analysis

Embeddings and retrieval are **fully local** — zero API cost at query time for those steps. Cost comes from generation only.

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|---|---|---|
| Claude Haiku 4.5 | $0.80 | $4.00 |

**Typical query cost:** ~800 input tokens (system prompt + 4 retrieved chunks + question) + ~300 output tokens ≈ **~$0.0018/query**

| Volume | Est. Monthly Cost |
|---|---|
| 10 queries/day | ~$0.54 |
| 50 queries/day | ~$2.70 |
| 200 queries/day | ~$10.80 |
| 1,000 queries/day | ~$54.00 |

Embedding model (`all-MiniLM-L6-v2`) runs locally — **$0.00** at any volume. Switching to a cloud embedding API (Voyage AI, OpenAI) would add ~$0.0001/query.

**Scaling note:** For large runbook libraries (1,000+ docs), the retrieval step stays fast because ChromaDB uses approximate nearest-neighbor search. Generation cost scales linearly with query volume, not corpus size.

---

## Skills Demonstrated

This project is intentionally production-aligned — not a local toy:

- **RAG architecture** — end-to-end retrieval-augmented generation pipeline: ingest, embed, store, retrieve, generate
- **Vector search** — ChromaDB with cosine similarity, relevance scoring, debug panel exposing retrieved chunks
- **Prompt engineering** — tightly scoped system prompt that forces grounded answers and source citations
- **NLP / embeddings** — local sentence-transformers, semantic chunking strategy, overlap for context preservation
- **Linux systems ops** — systemd service management, Nginx reverse proxy, Cloudflare integration, port hygiene
- **AI/API integration** — structured prompting, error handling, API key hygiene
- **Security hygiene** — secrets in `.env` (gitignored), gunicorn bound to loopback only, Cloudflare as the public face

---

## 🗺️ Roadmap

- [ ] Incident-runbook integration — auto-retrieve relevant procedure on alert and include in Telegram notification
- [ ] Runbook upload via UI — drag-and-drop ingest without SSH access
- [ ] Multi-turn conversation — follow-up questions with session context
- [ ] Relevance score threshold — suppress low-confidence results
- [ ] PDF and plain text runbook support

---

## Author

**Diego Perez** · [github.com/ohdasdiego](https://github.com/ohdasdiego)
