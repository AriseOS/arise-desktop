import { randomUUID } from "node:crypto";
import { executeTaskPipeline } from "./quick-task-service.js";
import { TaskStatus } from "./task-state.js";
import { taskRegistry } from "./task-registry.js";
import type {
  CloudSiteTaskItem,
  CloudSiteTaskPlan,
} from "./cloud-client.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("site-task-batch-service");
const BATCH_RETENTION_MS = 6 * 60 * 60 * 1000;

export type SiteTaskBatchStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed";

export interface SiteTaskBatchItem {
  execution_task_id: string;
  site: string;
  normalized_site: string;
  domain: string;
  site_summary: string;
  task_index: number;
  task: CloudSiteTaskItem;
  prompt: string;
  status: string;
  error?: string;
  started_at?: string;
  completed_at?: string;
}

export interface SiteTaskBatch {
  batch_id: string;
  status: SiteTaskBatchStatus;
  created_at: string;
  updated_at: string;
  execution_mode: "serial";
  continue_on_error: boolean;
  generated_sites: number;
  total_tasks: number;
  started_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  items: SiteTaskBatchItem[];
  error?: string;
}

function newId(length = 8): string {
  return randomUUID().replace(/-/g, "").slice(0, length);
}

function buildExecutionPrompt(
  plan: CloudSiteTaskPlan,
  task: CloudSiteTaskItem,
  taskIndex: number,
  totalTasks: number,
): string {
  const rationale = task.rationale?.trim()
    ? `Extra context: ${task.rationale.trim()}`
    : "Extra context: none";

  return [
    "Use the browser to complete the website task below and provide a concise final result.",
    "",
    `Site: ${plan.normalized_site}`,
    `Domain: ${plan.domain}`,
    `Start URL: ${task.starting_url || plan.normalized_site}`,
    `Site summary: ${plan.site_summary}`,
    `Batch item: ${taskIndex} / ${totalTasks}`,
    `Task title: ${task.title}`,
    `Task goal: ${task.goal}`,
    `Task type: ${task.task_type}`,
    rationale,
    "",
    "Execution requirements:",
    "- Start from the provided Start URL.",
    "- Prefer publicly accessible pages only. Do not log in, sign up, pay, or access private data.",
    "- If you cannot fully complete the task, explain the blocking reason.",
    "- Finish with a concise final result instead of only describing the process.",
  ].join("\n");
}

class SiteTaskBatchService {
  private readonly batches = new Map<string, SiteTaskBatch>();

  createBatch(
    plans: CloudSiteTaskPlan[],
    opts?: { continueOnError?: boolean },
  ): SiteTaskBatch {
    const batchId = `site_batch_${newId(12)}`;
    const createdAt = new Date().toISOString();
    const continueOnError = opts?.continueOnError ?? true;
    const flatTasks = plans.flatMap((plan) => plan.tasks.map((task) => ({ plan, task })));
    const totalTasks = flatTasks.length;

    const items: SiteTaskBatchItem[] = flatTasks.map(({ plan, task }, index) => {
      const executionTaskId = newId(8);
      const prompt = buildExecutionPrompt(plan, task, index + 1, totalTasks);
      taskRegistry.create(executionTaskId, prompt);

      return {
        execution_task_id: executionTaskId,
        site: plan.site,
        normalized_site: plan.normalized_site,
        domain: plan.domain,
        site_summary: plan.site_summary,
        task_index: index + 1,
        task,
        prompt,
        status: TaskStatus.PENDING,
      };
    });

    const batch: SiteTaskBatch = {
      batch_id: batchId,
      status: items.length > 0 ? "pending" : "completed",
      created_at: createdAt,
      updated_at: createdAt,
      execution_mode: "serial",
      continue_on_error: continueOnError,
      generated_sites: plans.length,
      total_tasks: items.length,
      started_tasks: 0,
      completed_tasks: 0,
      failed_tasks: 0,
      items,
    };

    this.batches.set(batchId, batch);
    logger.info(
      { batchId, generatedSites: plans.length, totalTasks: items.length, continueOnError },
      "Created site task execution batch",
    );

    if (items.length > 0) {
      void this.runBatch(batchId);
    }

    return this.snapshot(batch);
  }

  getBatch(batchId: string): SiteTaskBatch | null {
    const batch = this.batches.get(batchId);
    return batch ? this.snapshot(batch) : null;
  }

  private async runBatch(batchId: string): Promise<void> {
    const batch = this.batches.get(batchId);
    if (!batch) return;

    batch.status = "running";
    batch.updated_at = new Date().toISOString();

    logger.info({ batchId, totalTasks: batch.total_tasks }, "Starting site task execution batch");

    for (const item of batch.items) {
      const state = taskRegistry.get(item.execution_task_id);
      if (!state) {
        item.status = TaskStatus.FAILED;
        item.error = "Task state missing before execution";
        batch.failed_tasks += 1;
        batch.updated_at = new Date().toISOString();
        continue;
      }

      batch.started_tasks += 1;
      item.status = TaskStatus.RUNNING;
      item.started_at = new Date().toISOString();
      batch.updated_at = new Date().toISOString();

      logger.info(
        {
          batchId,
          taskId: item.execution_task_id,
          taskIndex: item.task_index,
          title: item.task.title,
        },
        "Executing generated site task",
      );

      try {
        await executeTaskPipeline(state);
      } catch (err) {
        logger.warn(
          { batchId, taskId: item.execution_task_id, err },
          "Generated site task pipeline threw unexpectedly",
        );
      }

      const finalState = taskRegistry.get(item.execution_task_id);
      const finalStatus = finalState?.status ?? TaskStatus.FAILED;
      item.status = finalStatus;
      item.error = finalState?.error;
      item.completed_at = new Date().toISOString();

      if (finalStatus === TaskStatus.COMPLETED) {
        batch.completed_tasks += 1;
      } else {
        batch.failed_tasks += 1;
      }

      batch.updated_at = new Date().toISOString();

      if (!batch.continue_on_error && finalStatus !== TaskStatus.COMPLETED) {
        batch.error = `Task ${item.execution_task_id} failed and continue_on_error is false`;
        break;
      }
    }

    const stillPending = batch.items.filter((item) => item.status === TaskStatus.PENDING);
    if (stillPending.length > 0) {
      for (const item of stillPending) {
        item.status = TaskStatus.CANCELLED;
        item.error = "Skipped because an earlier task failed";
        item.completed_at = new Date().toISOString();
      }
    }

    batch.status = batch.failed_tasks > 0 && batch.completed_tasks === 0
      ? "failed"
      : "completed";
    batch.updated_at = new Date().toISOString();

    logger.info(
      {
        batchId,
        status: batch.status,
        completedTasks: batch.completed_tasks,
        failedTasks: batch.failed_tasks,
      },
      "Finished site task execution batch",
    );
  }

  private snapshot(batch: SiteTaskBatch): SiteTaskBatch {
    return {
      ...batch,
      items: batch.items.map((item) => ({
        ...item,
        task: { ...item.task },
      })),
    };
  }

  cleanup(maxAgeMs = BATCH_RETENTION_MS): number {
    const now = Date.now();
    let removed = 0;

    for (const [batchId, batch] of this.batches.entries()) {
      const ageMs = now - new Date(batch.updated_at).getTime();
      if (ageMs > maxAgeMs && (batch.status === "completed" || batch.status === "failed")) {
        this.batches.delete(batchId);
        removed += 1;
      }
    }

    if (removed > 0) {
      logger.info({ removed }, "Cleaned up old site task batches");
    }

    return removed;
  }
}

export const siteTaskBatchService = new SiteTaskBatchService();

setInterval(() => {
  try {
    siteTaskBatchService.cleanup();
  } catch {
    // best effort cleanup
  }
}, 30 * 60 * 1000).unref();
