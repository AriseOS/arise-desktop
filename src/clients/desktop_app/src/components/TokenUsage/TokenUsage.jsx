/**
 * TokenUsage Component
 *
 * Displays token usage statistics including input/output tokens,
 * cache statistics, cost, and budget progress.
 */

import React from 'react';

function TokenUsage({
  // Direct props
  inputTokens,
  outputTokens,
  cacheCreation,
  cacheRead,
  cost,
  // Object props (alternative)
  usage = {},
  budget = {},
  model = null,
  compact = false,
  showDetails = false,
}) {
  // Support both direct props and usage object
  const _inputTokens = inputTokens ?? usage.inputTokens ?? 0;
  const _outputTokens = outputTokens ?? usage.outputTokens ?? 0;
  const _cacheCreation = cacheCreation ?? usage.cacheCreationTokens ?? 0;
  const _cacheRead = cacheRead ?? usage.cacheReadTokens ?? 0;
  const _cost = cost ?? usage.estimatedCost ?? 0;
  const _budget = typeof budget === 'number' ? budget : budget?.maxCostUsd ?? null;

  const totalTokens = _inputTokens + _outputTokens;

  // Calculate budget percentage
  const budgetPercent = _budget ? Math.min((_cost / _budget) * 100, 100) : 0;
  const isWarning = budgetPercent >= 70 && budgetPercent < 90;
  const isExceeded = budgetPercent >= 90;

  // Format number with K/M suffix
  const formatNumber = (num) => {
    if (num >= 1000000) {
      return (num / 1000000).toFixed(1) + 'M';
    }
    if (num >= 1000) {
      return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
  };

  // Format cost
  const formatCost = (amount) => {
    return `$${amount.toFixed(4)}`;
  };

  // Compact version
  if (compact) {
    return (
      <div className={`token-usage-compact ${isWarning ? 'warning' : ''} ${isExceeded ? 'exceeded' : ''}`}>
        <span>🎯</span>
        <span className="compact-tokens">{formatNumber(totalTokens)} tokens</span>
        <span className="compact-divider">|</span>
        <span className="compact-cost">{formatCost(_cost)}</span>
        {_budget && (
          <>
            <span className="compact-divider">|</span>
            <span className={`compact-percent ${isWarning ? 'warning' : ''} ${isExceeded ? 'exceeded' : ''}`}>
              {Math.round(budgetPercent)}%
            </span>
          </>
        )}
      </div>
    );
  }

  return (
    <div className={`token-usage-indicator ${isWarning ? 'warning' : ''} ${isExceeded ? 'exceeded' : ''}`}>
      {/* Header */}
      <div className="usage-header">
        <span className="usage-icon">📊</span>
        <span className="usage-title">Token Usage</span>
        {model && <span className="model-badge">{model}</span>}
      </div>

      {/* Stats Grid */}
      <div className="usage-stats">
        <div className="stat">
          <span className="stat-label">Input</span>
          <span className="stat-value">{formatNumber(_inputTokens)}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Output</span>
          <span className="stat-value">{formatNumber(_outputTokens)}</span>
        </div>
        <div className="stat total">
          <span className="stat-label">Total</span>
          <span className="stat-value">{formatNumber(totalTokens)}</span>
        </div>
        <div className="stat cost">
          <span className="stat-label">Cost</span>
          <span className="stat-value">{formatCost(_cost)}</span>
        </div>
      </div>

      {/* Cache Stats */}
      {(_cacheCreation > 0 || _cacheRead > 0) && (
        <div className="cache-stats">
          <div className="cache-stat">
            <span className="cache-label">Cache Created:</span>
            <span className="cache-value">{formatNumber(_cacheCreation)}</span>
          </div>
          <div className="cache-stat">
            <span className="cache-label">Cache Read:</span>
            <span className="cache-value">{formatNumber(_cacheRead)}</span>
          </div>
        </div>
      )}

      {/* Budget Progress */}
      {_budget && (
        <div className="budget-progress">
          <div className="progress-header">
            <span className="progress-label">Budget Usage</span>
            <span className="progress-value">
              {formatCost(_cost)} / {formatCost(_budget)}
            </span>
          </div>
          <div className="progress-bar">
            <div
              className={`progress-fill ${isWarning ? 'warning' : ''} ${isExceeded ? 'exceeded' : ''}`}
              style={{ width: `${budgetPercent}%` }}
            />
          </div>
          <span className="progress-percent">{Math.round(budgetPercent)}% used</span>
        </div>
      )}

      {/* Warning Message */}
      {isWarning && !isExceeded && (
        <div className="budget-warning">
          <span>⚠️</span>
          <span>Approaching budget limit</span>
        </div>
      )}

      {isExceeded && (
        <div className="budget-warning exceeded">
          <span>🚨</span>
          <span>Budget limit reached</span>
        </div>
      )}
    </div>
  );
}

export default TokenUsage;
