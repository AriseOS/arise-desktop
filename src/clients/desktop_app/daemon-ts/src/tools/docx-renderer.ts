/**
 * DOCX Renderer — Markdown → DOCX via `docx` npm package.
 *
 * Parses Markdown tokens with `marked.lexer()` and maps them to docx paragraphs.
 */

import { writeFile } from "node:fs/promises";
import { mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import { marked, type Token, type Tokens } from "marked";
import {
  Document,
  Packer,
  Paragraph,
  TextRun,
  HeadingLevel,
  TableRow,
  TableCell,
  Table,
  WidthType,
  BorderStyle,
} from "docx";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("docx-renderer");

// ===== Inline text parsing =====

/** Parse inline Markdown (bold, italic, code, links) into TextRun[]. */
function parseInlineTokens(tokens: Token[]): TextRun[] {
  const runs: TextRun[] = [];

  for (const token of tokens) {
    switch (token.type) {
      case "text":
        runs.push(new TextRun((token as Tokens.Text).text));
        break;
      case "strong":
        for (const child of (token as Tokens.Strong).tokens) {
          runs.push(
            new TextRun({
              text: (child as any).text ?? (child as any).raw ?? "",
              bold: true,
            }),
          );
        }
        break;
      case "em":
        for (const child of (token as Tokens.Em).tokens) {
          runs.push(
            new TextRun({
              text: (child as any).text ?? (child as any).raw ?? "",
              italics: true,
            }),
          );
        }
        break;
      case "codespan":
        runs.push(
          new TextRun({
            text: (token as Tokens.Codespan).text,
            font: "Courier New",
            size: 20, // 10pt
          }),
        );
        break;
      case "link":
        runs.push(
          new TextRun({
            text: (token as Tokens.Link).text,
            color: "0563C1",
            underline: {},
          }),
        );
        break;
      default:
        // Fallback: use raw text
        if ((token as any).raw) {
          runs.push(new TextRun((token as any).raw));
        }
        break;
    }
  }

  return runs;
}

/** Convert a plain text string to TextRun[] (for items without sub-tokens). */
function textToRuns(text: string): TextRun[] {
  return [new TextRun(text)];
}

// ===== Block-level token mapping =====

const HEADING_LEVELS: Record<number, (typeof HeadingLevel)[keyof typeof HeadingLevel]> = {
  1: HeadingLevel.HEADING_1,
  2: HeadingLevel.HEADING_2,
  3: HeadingLevel.HEADING_3,
  4: HeadingLevel.HEADING_4,
  5: HeadingLevel.HEADING_5,
  6: HeadingLevel.HEADING_6,
};

function convertTokensToParagraphs(tokens: Token[]): Paragraph[] {
  const paragraphs: Paragraph[] = [];

  for (const token of tokens) {
    switch (token.type) {
      case "heading": {
        const h = token as Tokens.Heading;
        paragraphs.push(
          new Paragraph({
            heading: HEADING_LEVELS[h.depth] ?? HeadingLevel.HEADING_1,
            children: h.tokens ? parseInlineTokens(h.tokens) : textToRuns(h.text),
          }),
        );
        break;
      }

      case "paragraph": {
        const p = token as Tokens.Paragraph;
        paragraphs.push(
          new Paragraph({
            children: p.tokens ? parseInlineTokens(p.tokens) : textToRuns(p.text),
          }),
        );
        break;
      }

      case "code": {
        const c = token as Tokens.Code;
        // Render code block as monospace paragraphs
        const lines = c.text.split("\n");
        for (const line of lines) {
          paragraphs.push(
            new Paragraph({
              children: [
                new TextRun({
                  text: line || " ",
                  font: "Courier New",
                  size: 20,
                }),
              ],
              shading: { fill: "F4F4F4" },
            }),
          );
        }
        break;
      }

      case "blockquote": {
        const bq = token as Tokens.Blockquote;
        const inner = convertTokensToParagraphs(bq.tokens);
        for (const p of inner) {
          paragraphs.push(
            new Paragraph({
              ...((p as any).options ?? {}),
              children: (p as any).root ?? [],
              indent: { left: 720 }, // 0.5 inch
              border: {
                left: {
                  style: BorderStyle.SINGLE,
                  size: 6,
                  color: "CCCCCC",
                  space: 4,
                },
              },
            }),
          );
        }
        break;
      }

      case "list": {
        const list = token as Tokens.List;
        for (let i = 0; i < list.items.length; i++) {
          const item = list.items[i];
          const inlineRuns = item.tokens
            ? parseInlineTokens(
                item.tokens.flatMap((t: Token) =>
                  t.type === "text" && (t as Tokens.Text).tokens
                    ? (t as Tokens.Text).tokens!
                    : [t],
                ),
              )
            : textToRuns(item.text);

          // Prepend bullet or number
          const prefix = list.ordered ? `${Number(list.start ?? 1) + i}. ` : "• ";
          paragraphs.push(
            new Paragraph({
              children: [new TextRun(prefix), ...inlineRuns],
              indent: { left: 720 },
            }),
          );
        }
        break;
      }

      case "table": {
        // Tables are handled separately in renderMarkdownToDocx() since
        // Table is not a Paragraph and needs to be a direct section child.
        break;
      }

      case "hr": {
        paragraphs.push(
          new Paragraph({
            children: [],
            border: {
              bottom: { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" },
            },
          }),
        );
        break;
      }

      case "space": {
        paragraphs.push(new Paragraph({ children: [] }));
        break;
      }

      default: {
        // Fallback: render raw text
        if ((token as any).raw) {
          paragraphs.push(
            new Paragraph({
              children: [new TextRun((token as any).raw)],
            }),
          );
        }
        break;
      }
    }
  }

  return paragraphs;
}

/**
 * Render Markdown content to a DOCX file.
 *
 * @param markdownContent - Markdown source text
 * @param title - Document title (rendered as Heading 1)
 * @param outputPath - Absolute path for the output DOCX
 */
export async function renderMarkdownToDocx(
  markdownContent: string,
  title: string,
  outputPath: string,
): Promise<void> {
  // 1. Parse Markdown into tokens
  const tokens = marked.lexer(markdownContent);

  // 2. Convert tokens to docx elements
  const contentElements = convertTokensToParagraphs(tokens);

  // 3. Separate Tables from Paragraphs for proper Document structure
  //    docx library needs tables and paragraphs as siblings in sections.children
  const children: (Paragraph | Table)[] = [
    new Paragraph({
      heading: HeadingLevel.TITLE,
      children: [new TextRun({ text: title, bold: true })],
    }),
    new Paragraph({ children: [] }), // spacing after title
  ];

  // Re-walk tokens to properly handle tables (since Table isn't a Paragraph)
  for (const token of tokens) {
    if (token.type === "table") {
      const tbl = token as Tokens.Table;
      const rows: TableRow[] = [];

      rows.push(
        new TableRow({
          children: tbl.header.map(
            (cell) =>
              new TableCell({
                children: [
                  new Paragraph({
                    children: cell.tokens
                      ? parseInlineTokens(cell.tokens)
                      : textToRuns(cell.text),
                  }),
                ],
                shading: { fill: "F0F0F0" },
              }),
          ),
        }),
      );

      for (const row of tbl.rows) {
        rows.push(
          new TableRow({
            children: row.map(
              (cell) =>
                new TableCell({
                  children: [
                    new Paragraph({
                      children: cell.tokens
                        ? parseInlineTokens(cell.tokens)
                        : textToRuns(cell.text),
                    }),
                  ],
                }),
            ),
          }),
        );
      }

      children.push(
        new Table({
          rows,
          width: { size: 100, type: WidthType.PERCENTAGE },
        }),
      );
    } else {
      const paras = convertTokensToParagraphs([token]);
      children.push(...paras);
    }
  }

  // 4. Build document
  const doc = new Document({
    sections: [{ children }],
  });

  // 5. Generate and write file
  const buffer = await Packer.toBuffer(doc);
  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, buffer);

  logger.info({ outputPath, size: buffer.length }, "DOCX generated");
}
