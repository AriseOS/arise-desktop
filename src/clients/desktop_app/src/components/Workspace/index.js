/**
 * Workspace Components
 *
 * Main components:
 * - WorkspaceTabs: Tab container with Agent/Browser/Files/Terminal tabs
 *
 * Existing components:
 * - FileBrowser: File tree display
 * - FilePreview: File content preview
 * - TerminalOutput: Terminal output display
 *
 * Tab components:
 * - AgentTab: Execution details (thinking, toolkit, memory, result)
 * - BrowserTab: Browser screenshot view
 * - FilesTab: File browser wrapper
 * - TerminalTab: Terminal output wrapper
 */

// Main workspace component
export { default as WorkspaceTabs } from './WorkspaceTabs';

// Existing components
export { default as FileBrowser } from './FileBrowser';
export { default as FilePreview } from './FilePreview';
export { default as TerminalOutput } from './TerminalOutput';

// Tab components
export * from './tabs';

// Import styles
import './Workspace.css';
import './WorkspaceTabs.css';
