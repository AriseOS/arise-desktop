/**
 * AMI Task Planner — Memory-First task decomposition.
 *
 * Ported from ami_task_planner.py.
 *
 * Memory-First flow:
 * 1. Query Memory plan for the whole task → EXECUTION PLAN context
 * 2. Inject Memory context into LLM decomposition prompt
 * 3. Decompose into atomic, self-contained subtasks
 * (workflow_guide injection to subtasks is skipped — handled by L2 runtime)
 */

import { Agent } from "@mariozechner/pi-agent-core";
import { getConfiguredModel, getAnthropicApiKey } from "../utils/config.js";
import {
  FINE_GRAINED_DECOMPOSE_PROMPT,
  DEFAULT_WORKER_DESCRIPTIONS,
  DECOMPOSE_SYSTEM_MESSAGE,
} from "../prompts/task-decomposition.js";
import {
  type AMISubtask,
  createSubtask,
} from "./schemas.js";
import { Action } from "../events/types.js";
import type { SSEEmitter } from "../events/emitter.js";
import { agentPrompt, requireApiKey, debugStreamSimple } from "../utils/agent-helpers.js";
import { createLogger } from "../utils/logging.js";
import {
  MemoryToolkit,
  type MemoryPlanData,
} from "../tools/memory-tools.js";

const logger = createLogger("task-planner");

// ===== AMITaskPlanner =====

export class AMITaskPlanner {
  private taskId: string;
  private emitter?: SSEEmitter;
  private apiKey?: string;
  private userId?: string;
  private memoryApiBaseUrl: string;
  private workerDescriptions: Record<string, string>;

  constructor(opts: {
    taskId: string;
    emitter?: SSEEmitter;
    apiKey?: string;
    userId?: string;
    memoryApiBaseUrl: string;
    workerDescriptions?: Record<string, string>;
  }) {
    this.taskId = opts.taskId;
    this.emitter = opts.emitter;
    this.apiKey = opts.apiKey;
    this.userId = opts.userId;
    this.memoryApiBaseUrl = opts.memoryApiBaseUrl;
    this.workerDescriptions = opts.workerDescriptions ?? DEFAULT_WORKER_DESCRIPTIONS;

    logger.info(
      { taskId: this.taskId },
      "AMITaskPlanner initialized",
    );
  }

  // ===== Main Entry Point =====

  async decomposeAndQueryMemory(task: string): Promise<AMISubtask[]> {
    logger.info(
      { task: task.slice(0, 100) },
      "Memory-First decomposing task",
    );

    // L1 Planner: Query Memory for execution plan context
    let memoryContext = "";
    try {
      this.emitter?.emit({
        action: Action.decompose_progress,
        task_id: this.taskId,
        progress: 0.1,
        message: "Querying memory...",
        is_final: false,
      });

      const memoryToolkit = new MemoryToolkit({
        memoryApiBaseUrl: this.memoryApiBaseUrl,
        apiKey: this.apiKey,
        userId: this.userId,
        taskId: this.taskId,
        emitter: this.emitter,
      });

      const planResult = await memoryToolkit.planTask(task);
      const memoryPlan = planResult.memory_plan;
      memoryContext = AMITaskPlanner.formatMemoryPlanForDecompose(memoryPlan);

      logger.info(
        {
          coverage: memoryPlan.coverage,
          stepsCount: memoryPlan.steps.length,
          preferencesCount: memoryPlan.preferences.length,
          contextLen: memoryContext.length,
        },
        "L1 Planner memory context built",
      );

      // Determine memory level (matches Python ami_task_planner.py:300-315)
      const hasPhrase = memoryPlan.steps.some(
        (s) => s.source === "phrase" && s.phrase_id,
      );
      const level = memoryPlan.steps.length > 0
        ? (hasPhrase ? "L1" : "L2")
        : "L3";

      // Emit memory_level event
      this.emitter?.emit({
        action: Action.memory_level,
        task_id: this.taskId,
        level,
        reason: "PlannerAgent Memory analysis",
        states_count: memoryPlan.steps.length,
        method: "planner_agent",
      });

      // Emit human-readable memory report as agent_report
      const memoryReport = AMITaskPlanner.buildMemoryReport(memoryPlan, level);
      this.emitter?.emitAgentReport(memoryReport, "info");
    } catch (err) {
      const isTimeout = err instanceof Error && err.message.includes("timed out");
      if (isTimeout) {
        logger.warn({ err }, "L1 Planner memory query timed out, proceeding without memory context");
        this.emitter?.emitAgentReport("Memory query timed out, proceeding without memory context", "warning");
      } else {
        logger.warn({ err }, "L1 Planner memory query failed, proceeding without memory context");
      }
    }

    // Decompose with memory context injected into prompt
    const subtasks = await this.fineGrainedDecompose(task, memoryContext);

    // Emit final decomposition event
    this.emitDecomposeResult(subtasks);

    return subtasks;
  }

  // ===== Fine-Grained Decomposition =====

  async fineGrainedDecompose(
    task: string,
    memoryContext = "",
  ): Promise<AMISubtask[]> {
    logger.info("Fine-grained decomposing task...");

    // Emit progress
    this.emitter?.emit({
      action: Action.decompose_progress,
      task_id: this.taskId,
      progress: 0.3,
      message: "Analyzing task...",
      is_final: false,
    });

    // Build the prompt
    // Replace {workers_info} and {memory_context} BEFORE {task} to prevent
    // user-controlled task text from being interpreted as template variables.
    const workersInfo = this.buildWorkersInfo();
    const prompt = FINE_GRAINED_DECOMPOSE_PROMPT
      .replace("{workers_info}", workersInfo)
      .replace("{memory_context}", memoryContext)
      .replace("{task}", task);

    logger.info({ promptLen: prompt.length }, "Decompose prompt built");

    // Validate API key before creating agent (prevents hang on missing key)
    const resolvedApiKey = requireApiKey(this.apiKey ?? getAnthropicApiKey());

    // Call LLM for decomposition using a one-shot Agent
    const model = getConfiguredModel();
    const agent = new Agent({
      initialState: {
        systemPrompt: DECOMPOSE_SYSTEM_MESSAGE,
        model,
        tools: [],
        messages: [],
        thinkingLevel: "off",
      },
      getApiKey: async () => resolvedApiKey,
      streamFn: debugStreamSimple,
    });

    await agentPrompt(agent, prompt);

    // Extract text from response
    const messages = agent.state.messages;
    const lastAssistant = [...messages]
      .reverse()
      .find((m: any) => m.role === "assistant");

    let responseText = "";
    if (lastAssistant && "content" in lastAssistant) {
      const content = lastAssistant.content;
      if (typeof content === "string") {
        responseText = content;
      } else if (Array.isArray(content)) {
        responseText = content
          .filter((c: any) => c.type === "text")
          .map((c: any) => c.text ?? "")
          .join("\n");
      }
    }

    if (!responseText) {
      throw new Error("Fine-grained decomposition returned empty response");
    }

    logger.info(
      { responseLen: responseText.length },
      "Decompose raw response received",
    );

    // Parse XML
    const subtasks = this.parseXmlSubtasks(responseText);

    // Log each subtask
    const typeCounts: Record<string, number> = {};
    for (const st of subtasks) {
      typeCounts[st.agentType] = (typeCounts[st.agentType] ?? 0) + 1;
      logger.info(
        {
          id: st.id,
          type: st.agentType,
          deps: st.dependsOn,
          content: st.content.slice(0, 120),
        },
        "Subtask parsed",
      );
    }
    logger.info(
      { count: subtasks.length, types: typeCounts },
      "Fine-grained decomposition complete",
    );

    // Emit progress
    this.emitter?.emit({
      action: Action.decompose_progress,
      task_id: this.taskId,
      progress: 0.8,
      message: `Created ${subtasks.length} subtasks`,
      is_final: false,
    });

    return subtasks;
  }

  // ===== XML Parsing =====

  parseXmlSubtasks(responseText: string): AMISubtask[] {
    const subtasks: AMISubtask[] = [];

    // Extract <tasks>...</tasks> block
    const tasksMatch = responseText.match(/<tasks>([\s\S]*?)<\/tasks>/i);
    if (!tasksMatch) {
      logger.warn("No <tasks> block found, trying JSON fallback");
      return this.parseCoarseSubtasks(responseText);
    }

    const tasksContent = tasksMatch[1];

    // Extract individual <task> elements with attributes
    const taskPattern = /<task\s+([^>]*)>([\s\S]*?)<\/task>/gi;
    let match: RegExpExecArray | null;
    let index = 0;

    while ((match = taskPattern.exec(tasksContent)) !== null) {
      index++;
      const attrsStr = match[1];
      const content = match[2].trim();

      // Parse attributes
      let taskId = String(index);
      let agentType = "browser";
      let dependsOn: string[] = [];

      // Extract id
      const idMatch = attrsStr.match(/id=["']([^"']+)["']/i);
      if (idMatch) taskId = idMatch[1].trim();

      // Extract type
      const typeMatch = attrsStr.match(/type=["']([^"']+)["']/i);
      if (typeMatch) {
        agentType = typeMatch[1].toLowerCase().trim();
        if (!["browser", "document", "code", "multi_modal"].includes(agentType)) {
          logger.warn({ agentType }, "Unknown agent type, inferring from content");
          agentType = AMITaskPlanner.inferAgentType(content);
        }
      } else {
        agentType = AMITaskPlanner.inferAgentType(content);
      }

      // Extract depends_on
      const depsMatch = attrsStr.match(/depends_on=["']([^"']+)["']/i);
      if (depsMatch) {
        dependsOn = depsMatch[1]
          .split(",")
          .map((d) => d.trim())
          .filter(Boolean);
      }

      subtasks.push(
        createSubtask({ id: taskId, content, agentType, dependsOn }),
      );
    }

    // Fallback: simple <task>content</task> without attributes
    if (subtasks.length === 0) {
      const simplePattern = /<task>([\s\S]*?)<\/task>/gi;
      let simpleIndex = 0;
      let simpleMatch: RegExpExecArray | null;
      while ((simpleMatch = simplePattern.exec(tasksContent)) !== null) {
        simpleIndex++;
        const content = simpleMatch[1].trim();
        const agentType = AMITaskPlanner.inferAgentType(content);
        subtasks.push(
          createSubtask({
            id: String(simpleIndex),
            content,
            agentType,
            dependsOn: [],
          }),
        );
      }
    }

    if (subtasks.length === 0) {
      logger.warn("No <task> elements found, trying JSON fallback");
      return this.parseCoarseSubtasks(responseText);
    }

    return subtasks;
  }

  // ===== JSON Fallback =====

  private parseCoarseSubtasks(responseText: string): AMISubtask[] {
    // Try to extract JSON from the response
    const jsonMatch = responseText.match(/\{[\s\S]*"subtasks"[\s\S]*\}/);
    if (!jsonMatch) {
      throw new Error("Could not parse decomposition response (no XML or JSON)");
    }

    try {
      const parsed = JSON.parse(jsonMatch[0]);
      const items = parsed.subtasks;
      if (!Array.isArray(items)) {
        throw new Error("subtasks is not an array");
      }

      return items.map((item: any, i: number) =>
        createSubtask({
          id: String(item.id ?? i + 1),
          content: item.content ?? "",
          agentType: item.type ?? "browser",
          dependsOn: item.depends_on ?? [],
        }),
      );
    } catch (e) {
      throw new Error(`Failed to parse JSON subtasks: ${e}`);
    }
  }

  // ===== Agent Type Inference =====

  static inferAgentType(content: string): string {
    const lower = content.toLowerCase();

    // Browser indicators
    const browserKeywords = [
      "search", "browse", "visit", "navigate", "website",
      "click", "extract", "scrape", "web", "google",
      "url", "page", "login", "form", "download",
    ];
    // Document indicators
    const docKeywords = [
      "write", "create", "report", "document", "excel",
      "powerpoint", "word", "pdf", "csv", "html",
      "summarize", "compile", "format", "table",
      "presentation", "spreadsheet",
    ];
    // Code indicators
    const codeKeywords = [
      "code", "script", "program", "debug", "git",
      "compile", "build", "deploy", "test", "api",
      "python", "javascript", "typescript", "npm", "pip",
    ];
    // Multi-modal indicators
    const mmKeywords = [
      "image", "photo", "video", "audio", "transcribe",
      "generate image", "analyze image", "ocr",
    ];

    const scores: Record<string, number> = {
      browser: 0,
      document: 0,
      code: 0,
      multi_modal: 0,
    };

    for (const kw of browserKeywords) if (lower.includes(kw)) scores.browser++;
    for (const kw of docKeywords) if (lower.includes(kw)) scores.document++;
    for (const kw of codeKeywords) if (lower.includes(kw)) scores.code++;
    for (const kw of mmKeywords) if (lower.includes(kw)) scores.multi_modal++;

    const maxScore = Math.max(...Object.values(scores));
    if (maxScore === 0) return "browser"; // default

    for (const [type, score] of Object.entries(scores)) {
      if (score === maxScore) return type;
    }
    return "browser";
  }

  // ===== Memory Plan Formatting =====

  /**
   * Format MemoryPlanData as context string for the decomposition prompt.
   *
   * Each step is a concrete action with optional Memory backing
   * (workflow_guide with URLs, clicks, operations).
   *
   * Returns empty string if no useful data.
   */
  static formatMemoryPlanForDecompose(memoryPlan: MemoryPlanData): string {
    const steps = memoryPlan.steps ?? [];
    const preferences = memoryPlan.preferences ?? [];

    if (steps.length === 0 && preferences.length === 0) {
      return "";
    }

    const lines: string[] = [
      "",
      "",
      "**EXECUTION PLAN** (from Memory analysis of user's past workflows)",
      "",
      "The following step plan was generated from the user's workflow memory. " +
        "Use it as the basis for your decomposition:",
      "- Steps with workflow details have proven URLs and operations — follow them.",
      "- Steps without workflow details need to be planned from scratch.",
      "- Adapt specific values (search keywords, filters) to the current task.",
      "",
    ];

    for (const step of steps) {
      let sourceTag = "";
      if (step.source === "phrase") {
        sourceTag = " [from Memory]";
      } else if (step.source === "graph") {
        sourceTag = " [from Memory graph]";
      }

      lines.push(`**Step ${step.index}**${sourceTag}: ${step.content}`);
      if (step.workflow_guide) {
        for (const guideLine of step.workflow_guide.split("\n")) {
          lines.push(`  ${guideLine}`);
        }
      }
      lines.push("");
    }

    if (preferences.length > 0) {
      lines.push("**User Preferences** (apply to all steps):");
      for (const pref of preferences) {
        lines.push(`- ${pref}`);
      }
    }

    return lines.join("\n");
  }

  // ===== Memory Report =====

  /**
   * Build a human-readable memory report for chat display.
   * Matches Python ami_task_planner.py _build_planner_agent_report().
   */
  static buildMemoryReport(memoryPlan: MemoryPlanData, level: string): string {
    if (!memoryPlan.steps || memoryPlan.steps.length === 0) {
      return `🧠 Memory analysis: **${level}** — No matching workflows found. Will explore from scratch.`;
    }

    // Build step list as HTML details
    const liItems = memoryPlan.steps.map((step) => {
      const sourceTag = ({ phrase: "Memory", graph: "graph", none: "new" } as Record<string, string>)[step.source] ?? step.source;
      const escapedContent = (step.content ?? "").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      return `<li>[${sourceTag}] ${escapedContent}</li>`;
    });

    let coverageHtml = "";
    if (liItems.length > 0) {
      coverageHtml =
        `\n\n<details><summary>Execution plan (${liItems.length} steps)</summary>` +
        `<ul>${liItems.join("")}</ul></details>`;
    }

    // Build preferences
    let prefsHtml = "";
    if (memoryPlan.preferences && memoryPlan.preferences.length > 0) {
      const prefItems = memoryPlan.preferences.map(
        (p: string) => `<li>${p.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</li>`,
      );
      prefsHtml =
        `\n\n<details><summary>User preferences (${prefItems.length})</summary>` +
        `<ul>${prefItems.join("")}</ul></details>`;
    }

    return `🧠 Memory analysis: **${level}**${coverageHtml}${prefsHtml}`;
  }

  // ===== Helpers =====

  private buildWorkersInfo(): string {
    return Object.entries(this.workerDescriptions)
      .map(([type, desc]) => `- **${type}**: ${desc}`)
      .join("\n");
  }

  private emitDecomposeResult(subtasks: AMISubtask[]): void {
    if (!this.emitter) return;

    const subtasksData = subtasks.map((st) => ({
      id: st.id,
      content: st.content,
      state: st.state,
      agent_type: st.agentType,
      memory_level: st.memoryLevel,
    }));

    this.emitter.emit({
      action: Action.decompose_progress,
      task_id: this.taskId,
      progress: 1.0,
      message: "Decomposition complete",
      sub_tasks: subtasksData,
      is_final: true,
    });
  }
}
