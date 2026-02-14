/**
 * PDF Renderer — Markdown → HTML → PDF via CDP Page.printToPDF.
 *
 * Uses the existing Electron Chromium (via BrowserSession) to render HTML to PDF.
 * No external dependencies required — marked is already in deps.
 */

import { writeFile } from "node:fs/promises";
import { mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import { marked } from "marked";
import { BrowserSession } from "../browser/browser-session.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("pdf-renderer");

function buildHtmlDocument(title: string, bodyHtml: string): string {
  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {
      font-family: -apple-system, "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
      margin: 40px;
      font-size: 14px;
      line-height: 1.6;
      color: #333;
    }
    h1 { font-size: 24px; margin-bottom: 16px; }
    h2 { font-size: 20px; }
    h3 { font-size: 16px; }
    code {
      background: #f4f4f4;
      padding: 2px 4px;
      border-radius: 3px;
      font-family: "SF Mono", "Fira Code", monospace;
      font-size: 13px;
    }
    pre {
      background: #f4f4f4;
      padding: 12px;
      border-radius: 4px;
      overflow-x: auto;
    }
    pre code {
      background: none;
      padding: 0;
    }
    table { border-collapse: collapse; width: 100%; margin: 12px 0; }
    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
    th { background: #f8f8f8; }
    blockquote {
      border-left: 3px solid #ccc;
      margin-left: 0;
      padding-left: 12px;
      color: #666;
    }
    img { max-width: 100%; }
    ul, ol { padding-left: 24px; }
  </style>
</head>
<body>
  <h1>${escapeHtml(title)}</h1>
  ${bodyHtml}
</body>
</html>`;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * Render Markdown content to a PDF file using CDP Page.printToPDF.
 *
 * @param markdownContent - Markdown source text
 * @param title - Document title (rendered as H1)
 * @param outputPath - Absolute path for the output PDF
 */
export async function renderMarkdownToPdf(
  markdownContent: string,
  title: string,
  outputPath: string,
): Promise<void> {
  // 1. Markdown → HTML
  const bodyHtml = await marked.parse(markdownContent);
  const fullHtml = buildHtmlDocument(title, bodyHtml);

  // 2. Get a browser session and claim a page for rendering
  const session = BrowserSession.getDaemonSession();
  if (!session) {
    throw new Error("No daemon browser session available for PDF rendering");
  }
  await session.ensureBrowser();

  // Create a temporary tab for rendering
  const [tabId, page] = await session.createNewTab();

  try {
    // 3. Set HTML content
    await page.setContent(fullHtml, { waitUntil: "networkidle" });

    // 4. Use CDP Page.printToPDF
    const cdpSession = await page.context().newCDPSession(page);
    try {
      const result = await cdpSession.send("Page.printToPDF", {
        printBackground: true,
        preferCSSPageSize: false,
        paperWidth: 8.27, // A4
        paperHeight: 11.69,
        marginTop: 0.4,
        marginBottom: 0.4,
        marginLeft: 0.4,
        marginRight: 0.4,
      });

      // 5. Write PDF to file
      const pdfBuffer = Buffer.from((result as any).data, "base64");
      await mkdir(dirname(outputPath), { recursive: true });
      await writeFile(outputPath, pdfBuffer);

      logger.info({ outputPath, size: pdfBuffer.length }, "PDF generated");
    } finally {
      await cdpSession.detach();
    }
  } finally {
    // Return the temporary tab to the pool
    await session.closeTab(tabId);
  }
}
