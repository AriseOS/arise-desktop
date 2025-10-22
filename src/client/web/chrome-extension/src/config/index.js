// Centralized configuration for workflows and metaflows

import { WORKFLOWS, DEFAULT_WORKFLOW, getWorkflow, getWorkflowKeys } from './workflows'
import { METAFLOWS, DEFAULT_METAFLOW, getMetaflow, getMetaflowKeys } from './metaflows'

// Workflow-Metaflow mapping
// Each workflow should have a corresponding metaflow with the same key
export const WORKFLOW_METAFLOW_MAP = {
  'allegro-coffee-collection': {
    workflowKey: 'allegro-coffee-collection',
    metaflowKey: 'allegro-coffee-collection',
    displayName: 'Allegro Coffee Collection',
    description: 'Collect coffee product information from Allegro'
  }
}

// Default configuration key
export const DEFAULT_CONFIG_KEY = 'allegro-coffee-collection'

// Get workflow and metaflow by config key
export function getConfig(configKey) {
  const config = WORKFLOW_METAFLOW_MAP[configKey] || WORKFLOW_METAFLOW_MAP[DEFAULT_CONFIG_KEY]
  return {
    ...config,
    workflow: getWorkflow(config.workflowKey),
    metaflow: getMetaflow(config.metaflowKey)
  }
}

// Get all available configuration keys
export function getConfigKeys() {
  return Object.keys(WORKFLOW_METAFLOW_MAP)
}

// Re-export for convenience
export {
  WORKFLOWS,
  DEFAULT_WORKFLOW,
  getWorkflow,
  getWorkflowKeys,
  METAFLOWS,
  DEFAULT_METAFLOW,
  getMetaflow,
  getMetaflowKeys
}
