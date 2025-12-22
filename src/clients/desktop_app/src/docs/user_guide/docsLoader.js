// Simple loader for user guide markdown docs (English and Chinese)
// Uses Vite's import.meta.glob to bundle .md files as raw strings.

export const DOC_TOPICS = [
  {
    id: 'overview-getting-started',
    file: '01-overview-and-getting-started.md',
    title: {
      en: 'Overview & Getting Started',
      zh: '概览与快速开始',
    },
  },
  {
    id: 'account-and-settings',
    file: '02-account-and-settings.md',
    title: {
      en: 'Accounts and Settings',
      zh: '账号与设置',
    },
  },
  {
    id: 'create-from-recording',
    file: '03-create-automation-from-recording.md',
    title: {
      en: 'Create Automation from a Recording',
      zh: '从录制创建自动化',
    },
  },
  {
    id: 'workflows-and-execution',
    file: '04-workflows-and-execution.md',
    title: {
      en: 'Workflows and Execution',
      zh: 'Workflow 与执行',
    },
  },
  {
    id: 'recordings-and-data',
    file: '05-recordings-and-data.md',
    title: {
      en: 'Recordings and Data',
      zh: '录制和数据管理',
    },
  },
  {
    id: 'advanced-and-faq',
    file: '06-advanced-and-faq.md',
    title: {
      en: 'Advanced Features and FAQ',
      zh: '高级功能与常见问题',
    },
  },
];

const docsEn = import.meta.glob('./en/*.md', { as: 'raw' });
const docsZh = import.meta.glob('./zh/*.md', { as: 'raw' });

export async function loadDoc(id, language) {
  const topic = DOC_TOPICS.find((t) => t.id === id) || DOC_TOPICS[0];
  const fileName = topic.file;

  const enPath = `./en/${fileName}`;
  const zhPath = `./zh/${fileName}`;

  try {
    if (language === 'zh' && docsZh[zhPath]) {
      return await docsZh[zhPath]();
    }
    if (docsEn[enPath]) {
      return await docsEn[enPath]();
    }
  } catch (error) {
    console.error('[docsLoader] Failed to load doc file:', error);
  }

  // Fallback: try any available English doc
  const enKeys = Object.keys(docsEn);
  if (enKeys.length > 0) {
    const firstKey = enKeys[0];
    return docsEn[firstKey]();
  }

  throw new Error(`Documentation not found for id: ${id}`);
}

export function getTopics(language) {
  return DOC_TOPICS.map((topic) => ({
    id: topic.id,
    title: topic.title[language] || topic.title.en,
  }));
}
