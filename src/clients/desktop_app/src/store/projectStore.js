/**
 * Project Store
 *
 * Manages multiple chat sessions (chatStores) at the project level.
 * Supports multi-turn conversations and task queuing.
 *
 * Ported from Eigent's projectStore with adaptations for 2ami.
 */

import { createStore } from 'zustand/vanilla';

// Initial project state
const createInitialProject = (projectId, name = null) => ({
  id: projectId,
  name: name || `Project ${projectId}`,
  chatStoreIds: [], // List of chatStore IDs in this project
  activeChatStoreId: null,
  queuedMessages: [], // Messages waiting to be sent
  historyId: null, // For tracking project history/replay
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
});

// Create the store
const projectStore = createStore((set, get) => ({
  // State
  projects: {},
  activeProjectId: null,

  // === Project Management ===

  /**
   * Create a new project
   */
  createProject: (projectId = null) => {
    const id = projectId || `project_${Date.now()}`;

    set((state) => ({
      projects: {
        ...state.projects,
        [id]: createInitialProject(id),
      },
      activeProjectId: id,
    }));

    return id;
  },

  /**
   * Get a project by ID
   */
  getProject: (projectId) => {
    return get().projects[projectId];
  },

  /**
   * Get the active project
   */
  getActiveProject: () => {
    const { projects, activeProjectId } = get();
    return activeProjectId ? projects[activeProjectId] : null;
  },

  /**
   * Set active project ID
   */
  setActiveProjectId: (projectId) => {
    set({ activeProjectId: projectId });
  },

  /**
   * Update a project
   */
  updateProject: (projectId, updates) => {
    set((state) => {
      const project = state.projects[projectId];
      if (!project) return state;

      return {
        projects: {
          ...state.projects,
          [projectId]: {
            ...project,
            ...updates,
            updatedAt: new Date().toISOString(),
          },
        },
      };
    });
  },

  /**
   * Remove a project
   */
  removeProject: (projectId) => {
    set((state) => {
      const newProjects = { ...state.projects };
      delete newProjects[projectId];

      return {
        projects: newProjects,
        activeProjectId: state.activeProjectId === projectId ? null : state.activeProjectId,
      };
    });
  },

  // === Chat Store Management within Project ===

  /**
   * Add a chat store to a project
   */
  addChatStoreToProject: (projectId, chatStoreId) => {
    set((state) => {
      const project = state.projects[projectId];
      if (!project) return state;

      // Don't add duplicates
      if (project.chatStoreIds.includes(chatStoreId)) {
        return {
          projects: {
            ...state.projects,
            [projectId]: {
              ...project,
              activeChatStoreId: chatStoreId,
              updatedAt: new Date().toISOString(),
            },
          },
        };
      }

      return {
        projects: {
          ...state.projects,
          [projectId]: {
            ...project,
            chatStoreIds: [...project.chatStoreIds, chatStoreId],
            activeChatStoreId: chatStoreId,
            updatedAt: new Date().toISOString(),
          },
        },
      };
    });
  },

  /**
   * Remove a chat store from a project
   */
  removeChatStoreFromProject: (projectId, chatStoreId) => {
    set((state) => {
      const project = state.projects[projectId];
      if (!project) return state;

      const newChatStoreIds = project.chatStoreIds.filter((id) => id !== chatStoreId);

      return {
        projects: {
          ...state.projects,
          [projectId]: {
            ...project,
            chatStoreIds: newChatStoreIds,
            activeChatStoreId:
              project.activeChatStoreId === chatStoreId
                ? newChatStoreIds[newChatStoreIds.length - 1] || null
                : project.activeChatStoreId,
            updatedAt: new Date().toISOString(),
          },
        },
      };
    });
  },

  /**
   * Set active chat store within a project
   */
  setActiveChatStoreId: (projectId, chatStoreId) => {
    set((state) => {
      const project = state.projects[projectId];
      if (!project) return state;

      return {
        projects: {
          ...state.projects,
          [projectId]: {
            ...project,
            activeChatStoreId: chatStoreId,
            updatedAt: new Date().toISOString(),
          },
        },
      };
    });
  },

  // === Message Queue ===

  /**
   * Add a message to the queue
   */
  queueMessage: (projectId, message) => {
    set((state) => {
      const project = state.projects[projectId];
      if (!project) return state;

      return {
        projects: {
          ...state.projects,
          [projectId]: {
            ...project,
            queuedMessages: [
              ...project.queuedMessages,
              {
                id: `queued_${Date.now()}`,
                ...message,
                queuedAt: new Date().toISOString(),
              },
            ],
            updatedAt: new Date().toISOString(),
          },
        },
      };
    });
  },

  /**
   * Remove a message from the queue
   */
  dequeueMessage: (projectId, messageId) => {
    set((state) => {
      const project = state.projects[projectId];
      if (!project) return state;

      return {
        projects: {
          ...state.projects,
          [projectId]: {
            ...project,
            queuedMessages: project.queuedMessages.filter((m) => m.id !== messageId),
            updatedAt: new Date().toISOString(),
          },
        },
      };
    });
  },

  /**
   * Get next queued message
   */
  getNextQueuedMessage: (projectId) => {
    const project = get().projects[projectId];
    return project?.queuedMessages[0] || null;
  },

  /**
   * Clear all queued messages
   */
  clearQueue: (projectId) => {
    set((state) => {
      const project = state.projects[projectId];
      if (!project) return state;

      return {
        projects: {
          ...state.projects,
          [projectId]: {
            ...project,
            queuedMessages: [],
            updatedAt: new Date().toISOString(),
          },
        },
      };
    });
  },

  // === Helpers ===

  /**
   * Get all chat store IDs for a project
   */
  getChatStoreIds: (projectId) => {
    const project = get().projects[projectId];
    return project?.chatStoreIds || [];
  },

  /**
   * Get active chat store ID for the active project
   */
  getActiveChatStoreIdForActiveProject: () => {
    const { projects, activeProjectId } = get();
    if (!activeProjectId) return null;
    return projects[activeProjectId]?.activeChatStoreId || null;
  },

  // === Project Queries ===

  /**
   * Get all projects as an array
   */
  getAllProjects: () => {
    const { projects } = get();
    return Object.values(projects);
  },

  /**
   * Get project by ID
   */
  getProjectById: (projectId) => {
    return get().projects[projectId] || null;
  },

  /**
   * Check if a project is empty (no messages)
   */
  isEmptyProject: (project) => {
    if (!project) return true;
    return project.chatStoreIds.length === 0;
  },

  // === History ID Management ===

  /**
   * Set history ID for a project
   */
  setHistoryId: (projectId, historyId) => {
    set((state) => {
      const project = state.projects[projectId];
      if (!project) return state;

      return {
        projects: {
          ...state.projects,
          [projectId]: {
            ...project,
            historyId,
            updatedAt: new Date().toISOString(),
          },
        },
      };
    });
  },

  /**
   * Get history ID for a project
   */
  getHistoryId: (projectId) => {
    if (!projectId) {
      const { activeProjectId, projects } = get();
      if (!activeProjectId) return null;
      return projects[activeProjectId]?.historyId || null;
    }
    return get().projects[projectId]?.historyId || null;
  },

  // === Queued Messages Extended ===

  /**
   * Restore a queued message (for undo)
   */
  restoreQueuedMessage: (projectId, messageData) => {
    set((state) => {
      const project = state.projects[projectId];
      if (!project) return state;

      return {
        projects: {
          ...state.projects,
          [projectId]: {
            ...project,
            queuedMessages: [...project.queuedMessages, messageData],
            updatedAt: new Date().toISOString(),
          },
        },
      };
    });
  },

  // === Replay ===

  /**
   * Replay a project/task
   * Creates a new project with the same configuration for replay
   *
   * @param {string[]} taskIds - Task IDs to replay
   * @param {string} question - Question/content to replay
   * @param {string} projectId - Optional project ID
   * @param {string} historyId - Optional history ID
   * @returns {string} New project ID
   */
  replayProject: (taskIds, question = 'Replay task', projectId = null, historyId = null) => {
    const { createProject, setHistoryId } = get();

    // Create a new project for replay
    const newProjectId = createProject(projectId);

    // Set history ID if provided
    if (historyId) {
      setHistoryId(newProjectId, historyId);
    }

    // TODO: Initialize with replay configuration
    // This would typically create a chatStore and start the replay

    return newProjectId;
  },

  // === Reset ===

  /**
   * Reset the store
   */
  reset: () => {
    set({
      projects: {},
      activeProjectId: null,
    });
  },
}));

export default projectStore;
