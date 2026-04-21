"""
rag_engine.py
The core RAG pipeline: retrieve relevant chunks, send to Claude, return grounded answer.
"""
import os
from anthropic import Anthropic
from src.vector_store import VectorStore

SYSTEM_PROMPT = """You are an IT operations assistant that helps engineers resolve incidents \
and follow procedures by answering questions based on internal runbooks.

You will be given a user question and a set of relevant runbook excerpts. Your job is to:

1. Answer ONLY from the provided runbook context. Do not invent procedures.
2. If the runbooks don't contain enough information, say so clearly.
3. Cite which runbook(s) you used by name at the end of your answer.
4. Be concise and action-oriented — engineers on-call need fast, clear steps.
5. If the answer involves commands, format them in code blocks.
6. If there are sequential steps, number them.

Never guess. Never fabricate commands or procedures not in the provided context."""


class RAGEngine:
    def __init__(self):
        self.vector_store = VectorStore()
        self.client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        self.model = "claude-haiku-4-5-20251001"

    def query(self, question: str, top_k: int = 4) -> dict:
        """Answer a question using retrieval-augmented generation."""
        # Step 1: Retrieve relevant chunks
        retrieved = self.vector_store.search(question, top_k=top_k)

        if not retrieved:
            return {
                "answer": "No runbooks have been indexed yet. Run `python ingest.py` first.",
                "sources": [],
                "chunks_used": 0,
            }

        # Step 2: Build context from retrieved chunks
        context_parts = []
        sources = set()
        for i, chunk in enumerate(retrieved, 1):
            context_parts.append(
                f"[Runbook: {chunk['source']}]\n{chunk['text']}"
            )
            sources.add(chunk["source"])

        context = "\n\n---\n\n".join(context_parts)

        # Step 3: Send to Claude
        user_message = f"""Here are the relevant runbook excerpts:

{context}

---

Question: {question}

Answer the question based only on the runbooks above."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        answer = response.content[0].text

        return {
            "answer": answer,
            "sources": sorted(sources),
            "chunks_used": len(retrieved),
            "retrieved_chunks": [
                {"source": c["source"], "score": c["score"], "preview": c["text"][:200]}
                for c in retrieved
            ],
        }

    def document_count(self) -> int:
        return self.vector_store.document_count()

    def chunk_count(self) -> int:
        return self.vector_store.chunk_count()
