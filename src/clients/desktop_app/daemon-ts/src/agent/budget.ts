/**
 * Budget Tracker — tracks LLM cost per task.
 *
 * Ported from the budget tracking concept in the Python daemon.
 * Uses pi-ai response.usage.cost data when available.
 */

import { createLogger } from "../utils/logging.js";

const logger = createLogger("budget");

// ===== Budget Tracker =====

export class BudgetTracker {
  private _totalCost = 0;
  private _totalInputTokens = 0;
  private _totalOutputTokens = 0;
  private _callCount = 0;
  private _budgetLimit: number;
  private _taskId: string;

  constructor(taskId: string, budgetLimit = Infinity) {
    this._taskId = taskId;
    this._budgetLimit = budgetLimit;
  }

  get totalCost(): number {
    return this._totalCost;
  }

  get totalInputTokens(): number {
    return this._totalInputTokens;
  }

  get totalOutputTokens(): number {
    return this._totalOutputTokens;
  }

  get callCount(): number {
    return this._callCount;
  }

  get isOverBudget(): boolean {
    return this._totalCost >= this._budgetLimit;
  }

  /**
   * Record usage from a pi-ai response.
   * pi-ai Usage type: { input, output, cacheRead, cacheWrite, totalTokens, cost: { total, ... } }
   */
  recordUsage(usage: {
    input?: number;
    output?: number;
    totalTokens?: number;
    cost?: { total?: number };
  }): void {
    this._callCount++;

    if (usage.input) {
      this._totalInputTokens += usage.input;
    }
    if (usage.output) {
      this._totalOutputTokens += usage.output;
    }

    const cost = usage.cost?.total ?? 0;
    this._totalCost += cost;

    logger.debug(
      {
        taskId: this._taskId,
        callCount: this._callCount,
        inputTokens: usage.input,
        outputTokens: usage.output,
        cost,
        totalCost: this._totalCost,
      },
      "Usage recorded",
    );

    if (this.isOverBudget) {
      logger.warn(
        {
          taskId: this._taskId,
          totalCost: this._totalCost,
          budgetLimit: this._budgetLimit,
        },
        "Budget limit exceeded",
      );
    }
  }

  /**
   * Get a summary of token usage.
   */
  getSummary(): {
    totalCost: number;
    totalInputTokens: number;
    totalOutputTokens: number;
    callCount: number;
    isOverBudget: boolean;
  } {
    return {
      totalCost: this._totalCost,
      totalInputTokens: this._totalInputTokens,
      totalOutputTokens: this._totalOutputTokens,
      callCount: this._callCount,
      isOverBudget: this.isOverBudget,
    };
  }

  /**
   * Reset all counters.
   */
  reset(): void {
    this._totalCost = 0;
    this._totalInputTokens = 0;
    this._totalOutputTokens = 0;
    this._callCount = 0;
  }
}
