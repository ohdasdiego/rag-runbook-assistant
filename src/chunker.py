"""
chunker.py
Splits markdown runbooks into semantically meaningful chunks.
Respects header boundaries where possible — avoids cutting procedures in half.
"""
import re


def chunk_markdown(text: str, source: str, max_chunk_size: int = 800, overlap: int = 100) -> list[dict]:
    """
    Split markdown into chunks, respecting header boundaries.

    Strategy:
    1. Split on H2 headers (## Section) — these are logical runbook sections
    2. If a section is too large, sub-split on H3, then by paragraphs
    3. Add overlap between chunks to preserve context
    """
    chunks = []
    chunk_id = 0

    # Split on H2 headers first
    sections = re.split(r"\n(?=## )", text)

    for section in sections:
        section = section.strip()
        if not section:
            continue

        if len(section) <= max_chunk_size:
            chunks.append({
                "id": f"{source}::chunk_{chunk_id}",
                "text": section,
                "source": source,
            })
            chunk_id += 1
        else:
            # Section is too large — split by paragraphs with overlap
            sub_chunks = _split_with_overlap(section, max_chunk_size, overlap)
            for sub in sub_chunks:
                chunks.append({
                    "id": f"{source}::chunk_{chunk_id}",
                    "text": sub,
                    "source": source,
                })
                chunk_id += 1

    return chunks


def _split_with_overlap(text: str, max_size: int, overlap: int) -> list[str]:
    """Split long text into overlapping chunks on paragraph boundaries."""
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= max_size:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                chunks.append(current.strip())
            # Start new chunk with overlap from end of previous
            if chunks and overlap > 0:
                tail = chunks[-1][-overlap:]
                current = f"{tail}\n\n{para}"
            else:
                current = para

    if current:
        chunks.append(current.strip())

    return chunks
