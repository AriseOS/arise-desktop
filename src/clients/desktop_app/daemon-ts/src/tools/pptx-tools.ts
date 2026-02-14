/**
 * PPTX Tools — PowerPoint presentation creation.
 *
 * Ported from pptx_toolkit.py.
 *
 * Tool: create_presentation — JSON slide definitions → PPTX file.
 *
 * Dependencies: pptxgenjs
 */

import { Type, type Static } from "@sinclair/typebox";
import type { AgentTool } from "@mariozechner/pi-agent-core";
import { resolve, basename } from "node:path";
import { mkdir } from "node:fs/promises";
import type { SSEEmitter } from "../events/emitter.js";
import { Action } from "../events/types.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("pptx-tools");

// ===== Lazy import =====

async function getPptxGenJS() {
  const mod = await import("pptxgenjs");
  // pptxgenjs exports differently in CJS vs ESM
  const PptxGenJS = (mod as any).default ?? mod;
  return PptxGenJS as { new (): any };
}

// ===== Schema =====

const createPresentationSchema = Type.Object({
  content: Type.String({
    description: `JSON string defining slides. Each slide is an object with optional fields:
- title/subtitle: For title slides
- heading: Slide heading
- bullet_points: Array of strings for bullet list
- table: { headers: string[], rows: string[][] }
- notes: Speaker notes
Example: [{"title":"My Deck","subtitle":"Q1 Report"},{"heading":"Overview","bullet_points":["Point 1","Point 2"]}]`,
  }),
  filename: Type.String({
    description: "Output filename (e.g., 'report.pptx')",
  }),
});

// ===== Slide Types =====

interface SlideDefinition {
  title?: string;
  subtitle?: string;
  heading?: string;
  bullet_points?: string[];
  table?: { headers: string[]; rows: (string | number)[][] };
  notes?: string;
  img_keywords?: string;
}

// ===== Tool Factory =====

export function createPptxTools(opts: {
  workingDir: string;
  taskId: string;
  emitter?: SSEEmitter;
}): AgentTool<any>[] {
  const { workingDir, taskId, emitter } = opts;

  const create_presentation: AgentTool<typeof createPresentationSchema> = {
    name: "create_presentation",
    label: "Create Presentation",
    description:
      "Create a PowerPoint (.pptx) presentation from JSON slide definitions. Supports title slides, bullet points, and tables.",
    parameters: createPresentationSchema,
    execute: async (_id, params) => {
      const PptxGenJS = await getPptxGenJS();

      // Resolve filename within working directory and validate path
      const filepath = resolve(workingDir, params.filename);
      const normalizedWorkingDir = resolve(workingDir);
      if (!filepath.startsWith(normalizedWorkingDir + "/") && filepath !== normalizedWorkingDir) {
        throw new Error(`Path traversal detected: "${params.filename}" resolves outside working directory`);
      }

      // Parse slide definitions
      let slides: SlideDefinition[];
      try {
        slides = JSON.parse(params.content);
        if (!Array.isArray(slides)) {
          throw new Error("Content must be a JSON array of slide objects");
        }
      } catch (err) {
        throw new Error(`Invalid slide JSON: ${err instanceof Error ? err.message : String(err)}`);
      }

      const pptx = new PptxGenJS();
      pptx.layout = "LAYOUT_WIDE";

      for (const slide of slides) {
        const s = pptx.addSlide();

        // Title slide
        if (slide.title) {
          s.addText(slide.title, {
            x: 0.5,
            y: 1.5,
            w: "90%",
            fontSize: 36,
            bold: true,
            align: "center",
          });
          if (slide.subtitle) {
            s.addText(slide.subtitle, {
              x: 0.5,
              y: 3.0,
              w: "90%",
              fontSize: 20,
              color: "666666",
              align: "center",
            });
          }
          continue;
        }

        // Content slides
        let yPos = 0.5;

        // Heading
        if (slide.heading) {
          s.addText(slide.heading, {
            x: 0.5,
            y: yPos,
            w: "90%",
            fontSize: 24,
            bold: true,
          });
          yPos += 0.8;
        }

        // Bullet points
        if (slide.bullet_points?.length) {
          const bullets = slide.bullet_points.map((bp) => ({
            text: bp,
            options: { bullet: true as const, fontSize: 16 },
          }));
          s.addText(bullets, {
            x: 0.5,
            y: yPos,
            w: "90%",
            lineSpacingMultiple: 1.5,
          });
          yPos += slide.bullet_points.length * 0.5;
        }

        // Table
        if (slide.table) {
          const { headers, rows } = slide.table;
          const tableRows: { text: string; options?: Record<string, unknown> }[][] = [];

          // Header row
          tableRows.push(
            headers.map((h) => ({
              text: h,
              options: { bold: true, fill: { color: "4472C4" }, color: "FFFFFF" },
            })),
          );

          // Data rows
          for (const row of rows) {
            tableRows.push(
              row.map((cell) => ({ text: String(cell) })),
            );
          }

          s.addTable(tableRows, {
            x: 0.5,
            y: yPos,
            w: 12,
            border: { pt: 1, color: "CFCFCF" },
            colW: headers.map(() => 12 / headers.length),
          });
        }

        // Speaker notes
        if (slide.notes) {
          s.addNotes(slide.notes);
        }
      }

      // Ensure directory exists
      const dir = resolve(filepath, "..");
      await mkdir(dir, { recursive: true });

      await pptx.writeFile({ fileName: filepath });

      emitter?.emit({
        action: Action.write_file,
        task_id: taskId,
        file_path: filepath,
        file_name: basename(filepath),
      });

      logger.info({ filepath, slideCount: slides.length }, "Presentation created");

      return {
        content: [
          {
            type: "text",
            text: `Presentation created: ${filepath} (${slides.length} slides)`,
          },
        ],
        details: undefined,
      };
    },
  };

  return [create_presentation];
}
