# Roadmap

Planned improvements and future features for the RAG Runbook Assistant.

---

## v1.0 — Current

- [x] Header-aware markdown chunker with paragraph overlap
- [x] ChromaDB vector store with local `all-MiniLM-L6-v2` embeddings
- [x] Claude-powered grounded answer generation with source citations
- [x] Web UI with example queries and debug panel (retrieved chunks + relevance scores)
- [x] `ingest.py` CLI with `--reset` flag for full re-indexing
- [x] systemd service, Nginx reverse proxy, Cloudflare deployment
- [x] `/api/stats` endpoint (document + chunk counts)

---

## v2.0 — Planned

### Incident-Runbook Integration
Connect the RAG Runbook Assistant to [ai-incident-logger](https://github.com/ohdasdiego/ai-incident-logger) so that when a threshold breach fires, the relevant runbook procedure is automatically retrieved and included in the Telegram alert.

- [ ] `alerter.py` calls `/api/query` on incident creation
- [ ] Runbook excerpt appended to Telegram alert message
- [ ] Dashboard shows linked runbook per incident

### Runbook Upload via UI
Allow engineers to add runbooks without SSH access.

- [ ] Drag-and-drop or paste interface in the web UI
- [ ] Server-side ingest triggered on upload
- [ ] Confirmation with chunk count per document

### Multi-turn Conversation
Support follow-up questions within the same session.

- [ ] Server-side session state (Flask session or simple in-memory store)
- [ ] Previous Q&A pairs included in the Claude prompt as context
- [ ] "New conversation" button to reset session

---

## Backlog

- [ ] Relevance score threshold — suppress results below a minimum similarity score
- [ ] Support PDF and plain text runbooks in addition to markdown
- [ ] `/api/query` rate limiting for public deployments
- [ ] Bulk re-index via API endpoint (no SSH required)
