function setQuestion(el) {
    document.getElementById("question").value = el.textContent;
    document.getElementById("question").focus();
}

function formatAnswer(text) {
    // Escape HTML first
    text = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    // Code blocks
    text = text.replace(/```(\w+)?\n([\s\S]*?)```/g, "<pre><code>$2</code></pre>");
    // Inline code
    text = text.replace(/`([^`]+)`/g, "<code>$1</code>");
    // Bold
    text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    return text;
}

async function askQuestion() {
    const questionEl = document.getElementById("question");
    const question = questionEl.value.trim();
    if (!question) return;

    const btn = document.getElementById("ask-btn");
    const btnText = btn.querySelector(".btn-text");
    const btnSpinner = btn.querySelector(".btn-spinner");
    const resultDiv = document.getElementById("result");

    btn.disabled = true;
    btnText.style.display = "none";
    btnSpinner.style.display = "inline-block";

    resultDiv.style.display = "block";
    resultDiv.innerHTML = '<div style="color:#6b7280;">Searching runbooks and generating answer...</div>';

    try {
        const res = await fetch("/api/query", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question }),
        });

        const data = await res.json();

        if (data.error) {
            resultDiv.innerHTML = `<div class="error">Error: ${data.error}</div>`;
            return;
        }

        let html = `<div class="answer">${formatAnswer(data.answer)}</div>`;

        if (data.sources && data.sources.length > 0) {
            html += '<div class="sources-section">';
            html += '<div class="sources-label">Sources</div>';
            html += '<div>';
            data.sources.forEach((src) => {
                html += `<span class="source-chip">${src}</span>`;
            });
            html += "</div>";
            html += `<button class="debug-toggle" onclick="toggleDebug()">Show retrieved chunks (${data.chunks_used})</button>`;
            html += '<div id="debug-panel" class="debug-panel" style="display:none;">';
            data.retrieved_chunks.forEach((c) => {
                html += '<div class="chunk-preview">';
                html += `<div class="chunk-header"><span>${c.source}</span><span class="score">score: ${c.score.toFixed(3)}</span></div>`;
                html += `<div>${c.preview.replace(/</g, "&lt;")}...</div>`;
                html += "</div>";
            });
            html += "</div>";
            html += "</div>";
        }

        resultDiv.innerHTML = html;
    } catch (err) {
        resultDiv.innerHTML = `<div class="error">Network error: ${err.message}</div>`;
    } finally {
        btn.disabled = false;
        btnText.style.display = "inline";
        btnSpinner.style.display = "none";
    }
}

function toggleDebug() {
    const panel = document.getElementById("debug-panel");
    panel.style.display = panel.style.display === "none" ? "block" : "none";
}

// Allow Cmd/Ctrl+Enter to submit
document.getElementById("question").addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        askQuestion();
    }
});
