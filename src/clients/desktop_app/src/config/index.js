// Centralized configuration for workflows and metaflows

import { WORKFLOWS, getWorkflow, getWorkflowKeys } from './workflows'
import { METAFLOWS, getMetaflow, getMetaflowKeys } from './metaflows'

// Workflow-Metaflow mapping
// Each workflow should have a corresponding metaflow with the same key
export const WORKFLOW_METAFLOW_MAP = {
  'producthunt-weekly-leaderboard': {
    workflowKey: 'producthunt-weekly-leaderboard',
    metaflowKey: 'producthunt-weekly-leaderboard',
    displayName: 'ProductHunt Weekly Leaderboard',
    description: 'Scrape top products from Product Hunt weekly leaderboard with detailed information and team members'
  },
  'cross-market-product-selection': {
    workflowKey: 'cross-market-product-selection',
    metaflowKey: 'cross-market-product-selection',
    displayName: 'Cross-Market Product Selection',
    description: 'Analyze coffee product opportunities by comparing Poland (Allegro) and US (Amazon) markets'
  },
  'allegro-coffee-collection': {
    workflowKey: 'allegro-coffee-collection',
    metaflowKey: 'allegro-coffee-collection',
    displayName: 'Allegro Coffee Collection',
    description: 'Collect coffee product information from Allegro'
  },
  'amazon-coffee-collection': {
    workflowKey: 'amazon-coffee-collection',
    metaflowKey: 'amazon-coffee-collection',
    displayName: 'Amazon Coffee Collection',
    description: 'Collect coffee product information from Amazon'
  }
}

// Default configuration key
export const DEFAULT_CONFIG_KEY = 'cross-market-product-selection'

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
  getWorkflow,
  getWorkflowKeys,
  METAFLOWS,
  getMetaflow,
  getMetaflowKeys
}
