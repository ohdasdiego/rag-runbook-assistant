"""
vector_store.py
ChromaDB wrapper with sentence-transformers embeddings.
All local — no external API calls for embedding.
"""
import os
import chromadb
from chromadb.utils import embedding_functions


class VectorStore:
    def __init__(self, persist_dir: str = "./data/chroma", collection_name: str = "runbooks"):
        os.makedirs(persist_dir, exist_ok=True)

        # Use a small, fast, local model — runs on CPU fine
        self.embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )

        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedder,
        )

    def add_chunks(self, chunks: list[dict]):
        """Add chunks to the vector store.
        Each chunk must have: id, text, source (filename), metadata (optional).
        """
        if not chunks:
            return

        ids = [c["id"] for c in chunks]
        texts = [c["text"] for c in chunks]
        metadatas = [
            {"source": c["source"], **c.get("metadata", {})}
            for c in chunks
        ]

        self.collection.add(ids=ids, documents=texts, metadatas=metadatas)

    def search(self, query: str, top_k: int = 4) -> list[dict]:
        """Retrieve the top_k most relevant chunks for a query."""
        if self.collection.count() == 0:
            return []

        results = self.collection.query(
            query_texts=[query],
            n_results=min(top_k, self.collection.count()),
        )

        chunks = []
        for i in range(len(results["ids"][0])):
            chunks.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "source": results["metadatas"][0][i].get("source", "unknown"),
                "score": 1 - results["distances"][0][i],  # convert distance to similarity
            })
        return chunks

    def document_count(self) -> int:
        """Count unique source documents."""
        if self.collection.count() == 0:
            return 0
        all_metadata = self.collection.get()["metadatas"]
        return len(set(m["source"] for m in all_metadata))

    def chunk_count(self) -> int:
        return self.collection.count()

    def reset(self):
        """Clear the collection — used for re-ingestion."""
        self.client.delete_collection(self.collection.name)
        self.collection = self.client.get_or_create_collection(
            name="runbooks",
            embedding_function=self.embedder,
        )
