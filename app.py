"""
app.py
Flask web application for the RAG Runbook Assistant.
"""
import os
from flask import Flask, render_template, request, jsonify
from src.rag_engine import RAGEngine

app = Flask(__name__)
engine = RAGEngine()


@app.route("/")
def index():
    return render_template("index.html", doc_count=engine.document_count())


@app.route("/api/query", methods=["POST"])
def query():
    data = request.get_json()
    question = data.get("question", "").strip()

    if not question:
        return jsonify({"error": "Question is required"}), 400

    try:
        result = engine.query(question)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/stats")
def stats():
    return jsonify({
        "document_count": engine.document_count(),
        "chunk_count": engine.chunk_count(),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=False)
