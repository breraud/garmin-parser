"use client";

import { useState } from "react";

interface MarkdownPreviewProps {
  markdown: string;
}

export function MarkdownPreview({ markdown }: MarkdownPreviewProps) {
  const [copyStatus, setCopyStatus] = useState<string>("");

  async function copyMarkdown() {
    await navigator.clipboard.writeText(markdown);
    setCopyStatus("Markdown copie.");
    window.setTimeout(() => setCopyStatus(""), 2000);
  }

  function downloadMarkdown() {
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "garmin-activity.md";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="preview-section" aria-label="Markdown genere">
      <div className="preview-toolbar">
        <h2>Markdown genere</h2>
        <div className="preview-actions">
          <button type="button" onClick={copyMarkdown}>
            Copier
          </button>
          <button type="button" onClick={downloadMarkdown}>
            Telecharger .md
          </button>
        </div>
      </div>

      {copyStatus ? <p className="status-message">{copyStatus}</p> : null}

      <pre className="markdown-output">
        <code>{markdown}</code>
      </pre>
    </section>
  );
}

