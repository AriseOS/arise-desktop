/**
 * Lightweight i18n for backend SSE messages.
 *
 * Ported from i18n.py.
 *
 * Provides language detection and translation for user-visible messages
 * sent via SSE events (AgentReport, DecomposeProgress).
 */

// CJK Unicode ranges for language detection
const CJK_PATTERN =
  /[\u4e00-\u9fff\u3400-\u4dbf\u3000-\u303f\uff00-\uffef\u3040-\u309f\u30a0-\u30ff]/;

/**
 * Detect language from user input text.
 * Returns "zh" if text contains CJK characters, else "en".
 */
export function detectLanguage(text: string): "en" | "zh" {
  if (!text) return "en";
  return CJK_PATTERN.test(text) ? "zh" : "en";
}

// ===== Translation Table =====

const TRANSLATIONS: Record<string, { en: string; zh: string }> = {
  // Executor messages
  "executor.running": {
    en: "{progress} Executing: {preview}",
    zh: "{progress} 正在执行: {preview}",
  },
  "executor.completed": {
    en: "✓ {progress} Completed: {preview}",
    zh: "✓ {progress} 完成: {preview}",
  },
  "executor.failed": {
    en: "✗ {progress} Failed: {preview}{error_suffix}",
    zh: "✗ {progress} 失败: {preview}{error_suffix}",
  },
  "executor.api_retry": {
    en: "{progress} API error, retrying ({attempt}/{max_retries}) in {delay}s...",
    zh: "{progress} API 错误，正在重试 ({attempt}/{max_retries})，{delay}秒后...",
  },
  "executor.tasks_added": {
    en: "Added {count} follow-up tasks (total: {total})",
    zh: "已添加 {count} 个后续任务（共 {total} 个）",
  },

  // Error classification
  "executor.error.network": {
    en: "Network connection error, please check your network",
    zh: "网络连接错误，请检查网络",
  },
  "executor.error.rate_limit": {
    en: "API rate limited, please try again later",
    zh: "API 请求频率受限，请稍后重试",
  },
  "executor.error.server": {
    en: "API server unstable, please try again later",
    zh: "API 服务器不稳定，请稍后重试",
  },
  "executor.error.bad_request": {
    en: "API request error",
    zh: "API 请求错误",
  },
  "executor.error.unauthorized": {
    en: "API key invalid or expired",
    zh: "API 密钥无效或已过期",
  },
  "executor.error.unexpected": {
    en: "Unexpected error",
    zh: "意外错误",
  },

  // Planner decompose progress
  "planner.analyzing_memory": {
    en: "Analyzing Memory coverage...",
    zh: "正在分析 Memory 覆盖...",
  },
  "planner.decompose_complete": {
    en: "Decomposition complete",
    zh: "任务拆解完成",
  },
  "planner.querying_memory": {
    en: "Querying Memory for task workflow...",
    zh: "正在查询 Memory 工作流...",
  },
  "planner.analyzing_task": {
    en: "Analyzing task and creating atomic subtasks...",
    zh: "正在分析任务并创建原子子任务...",
  },
  "planner.created_subtasks": {
    en: "Created {count} atomic subtasks",
    zh: "已创建 {count} 个原子子任务",
  },
  "planner.analyzing_types": {
    en: "Analyzing task types...",
    zh: "正在分析任务类型...",
  },
  "planner.identified_subtasks": {
    en: "Identified {count} subtasks",
    zh: "已识别 {count} 个子任务",
  },

  // Memory report (old Reasoner path)
  "planner.memory.l1_found": {
    en: "**Found complete workflow memory (L1)**",
    zh: "**找到完整工作流记忆 (L1)**",
  },
  "planner.memory.l1_no_steps": {
    en: "**Found complete workflow memory (L1)** (no detailed steps)",
    zh: "**找到完整工作流记忆 (L1)**（无详细步骤）",
  },
  "planner.memory.l2_found": {
    en: "**Found partial navigation memory (L2)**",
    zh: "**找到部分导航记忆 (L2)**",
  },
  "planner.memory.l3_none": {
    en: "**No historical workflow memory found (L3)**",
    zh: "**未找到历史工作流记忆 (L3)**",
  },
  "planner.memory.view_steps": {
    en: "View workflow steps ({count} steps)",
    zh: "查看工作流步骤 ({count} 步)",
  },
  "planner.memory.view_path": {
    en: "View navigation path ({count} pages)",
    zh: "查看导航路径 ({count} 页)",
  },

  // Memory report (PlannerAgent path)
  "planner.memory.analysis_l3": {
    en: "**Memory analysis: no matching workflows found (L3)**",
    zh: "**Memory 分析：未找到匹配的工作流 (L3)**",
  },
  "planner.memory.analysis": {
    en: "**Memory analysis ({level})**",
    zh: "**Memory 分析 ({level})**",
  },
  "planner.memory.execution_plan": {
    en: "Execution plan ({count} steps)",
    zh: "执行计划 ({count} 步)",
  },
  "planner.memory.user_preferences": {
    en: "User preferences ({count})",
    zh: "用户偏好 ({count})",
  },

  // Quick task service
  "service.type.browser": {
    en: "Browser",
    zh: "浏览器",
  },
  "service.type.document": {
    en: "Document",
    zh: "文档",
  },
  "service.type.code": {
    en: "Code",
    zh: "代码",
  },
  "service.type.multi_modal": {
    en: "Multi-modal",
    zh: "多模态",
  },
  "service.task_decomposed": {
    en: "**Task decomposed into {count} subtasks**",
    zh: "**任务已拆解为 {count} 个子任务**",
  },
  "service.view_subtasks": {
    en: "View subtask list",
    zh: "查看子任务列表",
  },
  "service.all_completed": {
    en: "All {count} subtasks completed!",
    zh: "全部 {count} 个子任务执行完成！",
  },
  "service.execution_summary": {
    en: "Execution complete: {completed} succeeded, {failed} failed",
    zh: "执行完成：{completed} 成功，{failed} 失败",
  },
};

/**
 * Translate a message key to the given language.
 *
 * @param key - Dot-separated translation key (e.g. "executor.running")
 * @param lang - Language code ("en" or "zh"). Defaults to "en"
 * @param vars - Interpolation variables for template replacement
 * @returns Translated and interpolated string. Falls back to English, then to key.
 */
export function t(
  key: string,
  lang: string = "en",
  vars?: Record<string, string | number>,
): string {
  const entry = TRANSLATIONS[key];
  if (!entry) return key;

  const template =
    (lang === "zh" ? entry.zh : entry.en) ?? entry.en ?? key;

  if (!vars) return template;

  return template.replace(/\{(\w+)\}/g, (_, name) => {
    const val = vars[name];
    return val !== undefined ? String(val) : `{${name}}`;
  });
}
