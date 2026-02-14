/**
 * Tools Index — Re-exports all tool factory functions.
 *
 * Each factory creates AgentTool[] that can be passed to Agent.state.tools.
 */

// Core tools (always available)
export { createFileTools } from "./file-tools.js";
export { createTerminalTools } from "./terminal-tools.js";
export { createSearchTools } from "./search-tools.js";
export { createHumanTools } from "./human-tools.js";
export { createMemoryTools, MemoryToolkit } from "./memory-tools.js";
export type {
  QueryResult,
  CognitivePhrase,
  MemoryPlanResult,
  MemoryPlanData,
} from "./memory-tools.js";

// Browser tools
export { createBrowserTools } from "./browser-tools.js";

// Agent pipeline tools
export { createReplanTools } from "./replan-tools.js";

// Specialized tools (lazy-loaded by agent type)
export { createExcelTools } from "./excel-tools.js";
export { createPptxTools } from "./pptx-tools.js";
export { createImageTools } from "./image-tools.js";
export { createAudioTools } from "./audio-tools.js";
export { createVideoTools } from "./video-tools.js";
export { createCalendarTools } from "./calendar-tools.js";
export { createMarkItDownTools } from "./markitdown-tools.js";

// MCP tools (dynamic, async initialization)
export {
  MCPClient,
  createGmailTools,
  createGDriveTools,
  createNotionTools,
} from "./mcp-tools.js";
