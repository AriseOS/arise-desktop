/**
 * Store exports
 *
 * Central export point for all Zustand stores.
 */

// Agent store (existing)
export { useAgentStore, default as agentStore } from './agentStore';

// Chat store (new - vanilla Zustand for task lifecycle)
export { default as chatStore } from './chatStore';

// Project store (new - multi-project/session management)
export { default as projectStore } from './projectStore';

// Re-export types and constants
export { TaskStatus, TaskType } from './chatStore';
