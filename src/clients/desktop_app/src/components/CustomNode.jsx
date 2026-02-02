import React, { memo } from 'react';
import { Handle, Position } from 'reactflow';

// Icons removed to avoid dependency issues

// Semantic Color System
const AGENT_COLORS = {
  browser_agent: { border: '#06b6d4', bg: '#ecfeff', text: '#0e7490', label: 'BROWSER' }, // Cyan
  scraper_agent: { border: '#f97316', bg: '#ffedd5', text: '#c2410c', label: 'SCRAPER' }, // Orange
  variable: { border: '#a855f7', bg: '#f3e8ff', text: '#7e22ce', label: 'VARIABLE' }, // Purple
  foreach: { border: '#8b5cf6', bg: '#ede9fe', text: '#6d28d9', label: 'LOOP' }, // Violet
  loop: { border: '#8b5cf6', bg: '#ede9fe', text: '#6d28d9', label: 'LOOP' }, // Violet
  storage_agent: { border: '#10b981', bg: '#d1fae5', text: '#047857', label: 'STORAGE' }, // Emerald
  text_agent: { border: '#3b82f6', bg: '#dbeafe', text: '#1d4ed8', label: 'TEXT' }, // Blue
  tavily_agent: { border: '#ec4899', bg: '#fce7f3', text: '#be185d', label: 'TAVILY' }, // Pink
  // CognitivePhrase graph node types
  state: { border: '#3b82f6', bg: '#dbeafe', text: '#1d4ed8', label: 'STATE' }, // Blue for State
  intent_sequence: { border: '#10b981', bg: '#d1fae5', text: '#047857', label: 'SEQUENCE' }, // Green for IntentSequence
  default: { border: '#94a3b8', bg: '#f1f5f9', text: '#475569', label: 'STEP' } // Slate
};

const getAgentStyle = (type) => AGENT_COLORS[type] || AGENT_COLORS['default'];

const CustomNode = ({ id, data }) => {
  const { label, description, type, isLoop, agent, isExpanded, onToggleExpand, nodeType, intents, isNavigation } = data;
  // Map internal types to our color keys (v2 format uses 'agent' instead of 'agent_type')
  // For CognitivePhrase graph, use nodeType (state/intent_sequence)
  const styleKey = nodeType || agent || (isLoop ? 'loop' : 'default');
  const style = getAgentStyle(styleKey);

  // Check if this node is expandable (has intents to show)
  const isExpandable = nodeType === 'intent_sequence' && intents && intents.length > 0;

  return (
    <div style={{
      width: '280px',
      background: '#ffffff',
      borderRadius: '12px',
      boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
      border: '1px solid #e5e7eb',
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'row',
      position: 'relative',
      fontFamily: 'system-ui, -apple-system, sans-serif'
    }}>
      {/* Left Accent Strip */}
      <div style={{
        width: '6px',
        backgroundColor: style.border,
        flexShrink: 0
      }} />

      {/* Content Body */}
      <div style={{ padding: '16px', flexGrow: 1, display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {/* Meta Header */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '4px'
        }}>
          <span style={{
            fontSize: '11px',
            fontWeight: '700',
            color: style.text,
            letterSpacing: '0.05em',
            textTransform: 'uppercase'
          }}>
            {isNavigation ? 'NAVIGATION' : style.label}
          </span>

          {/* Collapsible Toggle for Loops or IntentSequences */}
          {(isLoop || isExpandable) && onToggleExpand && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onToggleExpand(id);
              }}
              style={{
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                padding: '4px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#6b7280',
                borderRadius: '4px'
              }}
              title={isExpanded ? "Collapse" : "Expand"}
            >
              {isExpanded ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="18 15 12 9 6 15"></polyline>
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="6 9 12 15 18 9"></polyline>
                </svg>
              )}
            </button>
          )}
        </div>

        {/* Title */}
        <div style={{
          fontSize: '15px',
          fontWeight: '600',
          color: '#111827',
          lineHeight: '1.4'
        }}>
          {label}
        </div>

        {/* Description */}
        {description && !isExpanded && (
          <div style={{
            fontSize: '13px',
            color: '#6b7280',
            lineHeight: '1.5',
            display: '-webkit-box',
            WebkitLineClamp: 3,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden'
          }}>
            {description}
          </div>
        )}

        {/* Expanded Intents List */}
        {isExpanded && isExpandable && (
          <div style={{
            fontSize: '12px',
            color: '#374151',
            background: '#f9fafb',
            borderRadius: '8px',
            padding: '8px',
            marginTop: '4px'
          }}>
            {intents.map((intent, idx) => (
              <div key={idx} style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '8px',
                marginBottom: idx < intents.length - 1 ? '6px' : 0,
                paddingBottom: idx < intents.length - 1 ? '6px' : 0,
                borderBottom: idx < intents.length - 1 ? '1px solid #e5e7eb' : 'none'
              }}>
                <span style={{
                  fontSize: '10px',
                  fontWeight: '600',
                  color: '#9ca3af',
                  minWidth: '18px'
                }}>
                  {idx + 1}.
                </span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: '500', color: '#111827' }}>
                    {intent.text || intent.type}
                  </div>
                  {intent.value && (
                    <div style={{ color: '#6b7280', fontSize: '11px', marginTop: '2px' }}>
                      {intent.value}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Connection Handles - All 4 sides for smart routing */}
      {/* Target: Left (Standard) */}
      <Handle
        type="target"
        position={Position.Left}
        id="target-left"
        style={{ width: '8px', height: '8px', background: '#9ca3af', left: '-4px', border: '2px solid white', zIndex: 10 }}
      />
      {/* Target: Top (Vertical Stack) */}
      <Handle
        type="target"
        position={Position.Top}
        id="target-top"
        style={{ width: '8px', height: '8px', background: '#9ca3af', top: '-4px', border: '2px solid white', zIndex: 10 }}
      />

      {/* Source: Right (Standard) */}
      <Handle
        type="source"
        position={Position.Right}
        id="source-right"
        style={{ width: '8px', height: '8px', background: '#9ca3af', right: '-4px', border: '2px solid white', zIndex: 10 }}
      />
      {/* Source: Bottom (Vertical Stack) */}
      <Handle
        type="source"
        position={Position.Bottom}
        id="source-bottom"
        style={{ width: '8px', height: '8px', background: '#9ca3af', bottom: '-4px', border: '2px solid white', zIndex: 10 }}
      />
    </div>
  );
};

export default memo(CustomNode);
