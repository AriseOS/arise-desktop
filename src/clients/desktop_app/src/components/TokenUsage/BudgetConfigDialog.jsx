/**
 * BudgetConfigDialog Component
 *
 * Dialog for configuring token usage budget limits.
 */

import React, { useState, useEffect } from 'react';

function BudgetConfigDialog({
  isOpen,
  onClose,
  budget,
  onSave,
}) {
  const [maxCostUsd, setMaxCostUsd] = useState(budget?.maxCostUsd || '');
  const [warningThreshold, setWarningThreshold] = useState(budget?.warningThreshold || 0.8);

  // Reset form when dialog opens
  useEffect(() => {
    if (isOpen) {
      setMaxCostUsd(budget?.maxCostUsd || '');
      setWarningThreshold(budget?.warningThreshold || 0.8);
    }
  }, [isOpen, budget]);

  // Handle save
  const handleSave = () => {
    onSave({
      maxCostUsd: maxCostUsd ? parseFloat(maxCostUsd) : null,
      warningThreshold: warningThreshold,
    });
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="budget-config-overlay" onClick={onClose}>
      <div className="budget-config-dialog" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="dialog-header">
          <span>💰</span>
          <h3>Budget Configuration</h3>
          <button className="close-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="dialog-body">
          <div className="form-group">
            <label htmlFor="maxCost">Maximum Cost (USD)</label>
            <input
              id="maxCost"
              type="number"
              step="0.01"
              min="0"
              value={maxCostUsd}
              onChange={(e) => setMaxCostUsd(e.target.value)}
              placeholder="e.g., 1.00"
            />
            <span className="help-text">
              Leave empty for unlimited budget
            </span>
          </div>

          <div className="form-group">
            <label htmlFor="warningThreshold">Warning Threshold</label>
            <select
              id="warningThreshold"
              value={warningThreshold}
              onChange={(e) => setWarningThreshold(parseFloat(e.target.value))}
            >
              <option value="0.5">50%</option>
              <option value="0.6">60%</option>
              <option value="0.7">70%</option>
              <option value="0.8">80%</option>
              <option value="0.9">90%</option>
            </select>
            <span className="help-text">
              Show warning when budget usage exceeds this threshold
            </span>
          </div>
        </div>

        {/* Footer */}
        <div className="dialog-footer">
          <button className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={handleSave}>
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

export default BudgetConfigDialog;
