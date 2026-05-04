#!/usr/bin/env python3
"""
ingest.py
Reads all markdown files in ./runbooks/, chunks them, and loads them into ChromaDB.

Usage:
    python ingest.py           # append to existing index
    python ingest.py --reset   # wipe and rebuild from scratch
"""
import os
import sys
import argparse
from src.vector_store import VectorStore
from src.chunker import chunk_markdown


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Wipe index before ingesting")
    parser.add_argument("--runbooks-dir", default="./runbooks", help="Runbooks directory")
    args = parser.parse_args()

    store = VectorStore()

    if args.reset:
        print("Resetting vector store...")
        store.reset()

    runbook_files = [
        f for f in os.listdir(args.runbooks_dir)
        if f.endswith(".md")
    ]

    if not runbook_files:
        print(f"No markdown files found in {args.runbooks_dir}")
        sys.exit(1)

    print(f"Found {len(runbook_files)} runbooks")

    total_chunks = 0
    for filename in sorted(runbook_files):
        filepath = os.path.join(args.runbooks_dir, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        chunks = chunk_markdown(content, source=filename)
        store.add_chunks(chunks)
        total_chunks += len(chunks)
        print(f"  {filename} -> {len(chunks)} chunks")

    print(f"\nIngestion complete")
    print(f"   Documents: {store.document_count()}")
    print(f"   Total chunks: {store.chunk_count()}")


if __name__ == "__main__":
    main()
