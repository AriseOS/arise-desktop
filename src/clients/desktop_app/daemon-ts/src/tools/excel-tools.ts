/**
 * Excel Tools — Excel file creation and manipulation.
 *
 * Ported from excel_toolkit.py.
 *
 * Tools: create_workbook, read_excel, write_excel, update_cell,
 *        get_sheet_names, export_to_csv.
 *
 * Dependencies: exceljs
 */

import { Type, type Static } from "@sinclair/typebox";
import type { AgentTool } from "@mariozechner/pi-agent-core";
import { resolve, basename } from "node:path";
import { writeFile } from "node:fs/promises";
import type { SSEEmitter } from "../events/emitter.js";
import { Action } from "../events/types.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("excel-tools");

// ===== Lazy import ExcelJS =====

async function getExcelJS() {
  const mod = await import("exceljs");
  return mod.default ?? mod;
}

// ===== Helpers =====

function resolvePath(filename: string, workingDir: string): string {
  let resolved: string;
  if (filename.startsWith("/") || filename.startsWith("~")) {
    resolved = resolve(filename.replace(/^~/, process.env.HOME ?? "/tmp"));
  } else {
    resolved = resolve(workingDir, filename);
  }
  const normalizedWorkingDir = resolve(workingDir);
  if (!resolved.startsWith(normalizedWorkingDir + "/") && resolved !== normalizedWorkingDir) {
    throw new Error(`Path traversal detected: "${filename}" resolves outside working directory`);
  }
  return resolved;
}

// ===== Schemas =====

const createWorkbookSchema = Type.Object({
  filename: Type.String({ description: "Output filename (e.g., 'data.xlsx')" }),
  sheets: Type.Optional(
    Type.Array(Type.String(), {
      description: "Sheet names to create. Default: ['Sheet1']",
    }),
  ),
});

const readExcelSchema = Type.Object({
  filepath: Type.String({ description: "Path to Excel file" }),
  sheet_name: Type.Optional(
    Type.String({ description: "Sheet name to read. Default: first sheet." }),
  ),
  include_header: Type.Optional(
    Type.Boolean({ description: "Include header row. Default: true." }),
  ),
});

const writeExcelSchema = Type.Object({
  filepath: Type.String({ description: "Path to Excel file" }),
  data: Type.Array(Type.Array(Type.Unknown()), {
    description: "2D array of cell values to write",
  }),
  sheet_name: Type.Optional(
    Type.String({ description: "Sheet name. Default: first sheet." }),
  ),
  headers: Type.Optional(
    Type.Array(Type.String(), { description: "Header row values" }),
  ),
});

const updateCellSchema = Type.Object({
  filepath: Type.String({ description: "Path to Excel file" }),
  row: Type.Number({ description: "Row number (1-indexed)" }),
  col: Type.Number({ description: "Column number (1-indexed)" }),
  value: Type.Unknown({ description: "New cell value" }),
  sheet_name: Type.Optional(Type.String({ description: "Sheet name" })),
});

const getSheetNamesSchema = Type.Object({
  filepath: Type.String({ description: "Path to Excel file" }),
});

const exportToCsvSchema = Type.Object({
  filepath: Type.String({ description: "Path to Excel file" }),
  output_path: Type.String({ description: "Output CSV file path" }),
  sheet_name: Type.Optional(Type.String({ description: "Sheet name to export" })),
});

// ===== Tool Factory =====

export function createExcelTools(opts: {
  workingDir: string;
  taskId: string;
  emitter?: SSEEmitter;
}): AgentTool<any>[] {
  const { workingDir, taskId, emitter } = opts;

  const create_workbook: AgentTool<typeof createWorkbookSchema> = {
    name: "create_workbook",
    label: "Create Excel Workbook",
    description: "Create a new Excel (.xlsx) workbook with optional sheet names.",
    parameters: createWorkbookSchema,
    execute: async (_id, params) => {
      const ExcelJS = await getExcelJS();
      const filepath = resolvePath(params.filename, workingDir);
      const sheets = params.sheets ?? ["Sheet1"];

      const workbook = new ExcelJS.Workbook();
      for (const name of sheets) {
        workbook.addWorksheet(name);
      }

      await workbook.xlsx.writeFile(filepath);

      emitter?.emit({
        action: Action.write_file,
        task_id: taskId,
        file_path: filepath,
        file_name: basename(filepath),
      });

      return {
        content: [
          {
            type: "text",
            text: `Workbook created: ${filepath} with sheets: ${sheets.join(", ")}`,
          },
        ],
        details: undefined,
      };
    },
  };

  const read_excel: AgentTool<typeof readExcelSchema> = {
    name: "read_excel",
    label: "Read Excel",
    description: "Read data from an Excel file. Returns tab-separated rows.",
    parameters: readExcelSchema,
    execute: async (_id, params) => {
      const ExcelJS = await getExcelJS();
      const filepath = resolvePath(params.filepath, workingDir);
      const includeHeader = params.include_header ?? true;

      const workbook = new ExcelJS.Workbook();
      await workbook.xlsx.readFile(filepath);

      const sheet = params.sheet_name
        ? workbook.getWorksheet(params.sheet_name)
        : workbook.worksheets[0];

      if (!sheet) {
        throw new Error(
          `Sheet not found: ${params.sheet_name ?? "(no sheets)"}`,
        );
      }

      const rows: string[] = [];
      sheet.eachRow({ includeEmpty: false }, (row, rowNumber) => {
        if (!includeHeader && rowNumber === 1) return;
        const values = (row.values as unknown[])
          .slice(1) // ExcelJS row.values is 1-indexed (index 0 is undefined)
          .map((v) => String(v ?? ""));
        rows.push(values.join("\t"));
      });

      return {
        content: [
          {
            type: "text",
            text: rows.length > 0 ? rows.join("\n") : "(empty sheet)",
          },
        ],
        details: undefined,
      };
    },
  };

  const write_excel: AgentTool<typeof writeExcelSchema> = {
    name: "write_excel",
    label: "Write Excel",
    description: "Write data to an Excel file. Creates or overwrites the sheet.",
    parameters: writeExcelSchema,
    execute: async (_id, params) => {
      const ExcelJS = await getExcelJS();
      const filepath = resolvePath(params.filepath, workingDir);

      let workbook: InstanceType<typeof ExcelJS.Workbook>;
      try {
        workbook = new ExcelJS.Workbook();
        await workbook.xlsx.readFile(filepath);
      } catch {
        workbook = new ExcelJS.Workbook();
      }

      const sheetName = params.sheet_name ?? "Sheet1";
      let sheet = workbook.getWorksheet(sheetName);
      if (sheet) {
        workbook.removeWorksheet(sheet.id);
      }
      sheet = workbook.addWorksheet(sheetName);

      // Write headers
      if (params.headers) {
        sheet.addRow(params.headers);
      }

      // Write data rows
      for (const row of params.data) {
        sheet.addRow(row);
      }

      await workbook.xlsx.writeFile(filepath);

      emitter?.emit({
        action: Action.write_file,
        task_id: taskId,
        file_path: filepath,
        file_name: basename(filepath),
      });

      return {
        content: [
          {
            type: "text",
            text: `Written ${params.data.length} rows to ${filepath} (sheet: ${sheetName})`,
          },
        ],
        details: undefined,
      };
    },
  };

  const update_cell: AgentTool<typeof updateCellSchema> = {
    name: "update_cell",
    label: "Update Cell",
    description: "Update a specific cell value in an Excel file.",
    parameters: updateCellSchema,
    execute: async (_id, params) => {
      const ExcelJS = await getExcelJS();
      const filepath = resolvePath(params.filepath, workingDir);

      const workbook = new ExcelJS.Workbook();
      await workbook.xlsx.readFile(filepath);

      const sheet = params.sheet_name
        ? workbook.getWorksheet(params.sheet_name)
        : workbook.worksheets[0];

      if (!sheet) {
        throw new Error("Sheet not found");
      }

      sheet.getCell(params.row, params.col).value = params.value as any;
      await workbook.xlsx.writeFile(filepath);

      return {
        content: [
          {
            type: "text",
            text: `Cell (${params.row}, ${params.col}) updated in ${filepath}`,
          },
        ],
        details: undefined,
      };
    },
  };

  const get_sheet_names: AgentTool<typeof getSheetNamesSchema> = {
    name: "get_sheet_names",
    label: "Get Sheet Names",
    description: "Get all sheet names in an Excel workbook.",
    parameters: getSheetNamesSchema,
    execute: async (_id, params) => {
      const ExcelJS = await getExcelJS();
      const filepath = resolvePath(params.filepath, workingDir);

      const workbook = new ExcelJS.Workbook();
      await workbook.xlsx.readFile(filepath);

      const names = workbook.worksheets.map((ws: any) => ws.name);

      return {
        content: [
          {
            type: "text",
            text: `Sheets in ${basename(filepath)}: ${names.join(", ")}`,
          },
        ],
        details: undefined,
      };
    },
  };

  const export_to_csv: AgentTool<typeof exportToCsvSchema> = {
    name: "export_to_csv",
    label: "Export to CSV",
    description: "Export an Excel sheet to CSV format.",
    parameters: exportToCsvSchema,
    execute: async (_id, params) => {
      const ExcelJS = await getExcelJS();
      const filepath = resolvePath(params.filepath, workingDir);
      const outputPath = resolvePath(params.output_path, workingDir);

      const workbook = new ExcelJS.Workbook();
      await workbook.xlsx.readFile(filepath);

      const sheet = params.sheet_name
        ? workbook.getWorksheet(params.sheet_name)
        : workbook.worksheets[0];

      if (!sheet) {
        throw new Error("Sheet not found");
      }

      const rows: string[] = [];
      sheet.eachRow({ includeEmpty: false }, (row) => {
        const values = (row.values as unknown[])
          .slice(1)
          .map((v) => {
            const s = String(v ?? "");
            // CSV escape: quote fields containing comma, quote, or newline
            if (s.includes(",") || s.includes('"') || s.includes("\n")) {
              return `"${s.replace(/"/g, '""')}"`;
            }
            return s;
          });
        rows.push(values.join(","));
      });

      await writeFile(outputPath, rows.join("\n"), "utf-8");

      return {
        content: [
          {
            type: "text",
            text: `Exported ${rows.length} rows to CSV: ${outputPath}`,
          },
        ],
        details: undefined,
      };
    },
  };

  return [
    create_workbook,
    read_excel,
    write_excel,
    update_cell,
    get_sheet_names,
    export_to_csv,
  ];
}
