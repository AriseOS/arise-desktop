import React, { memo } from 'react';

const GroupNode = ({ data }) => {
    return (
        <div style={{
            width: '100%',
            height: '100%',
            backgroundColor: 'rgba(240, 244, 248, 0.5)', // Slate-50 with opacity
            border: '2px dashed #cbd5e1', // Slate-300 dashed
            borderRadius: '16px',
            position: 'relative',
            zIndex: -1, // Ensure it sits behind
            pointerEvents: 'none' // Allow clicking through to underlying grid if needed (though nodes are usually above)
        }}>
            <div style={{
                position: 'absolute',
                top: '-24px',
                left: '20px',
                backgroundColor: 'transparent',
                padding: '0 8px',
                color: '#94a3b8',
                fontSize: '12px',
                fontWeight: '600',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
            }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"></path>
                    <path d="M21 3v5h-5"></path>
                    <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"></path>
                    <path d="M8 16H3v5"></path>
                </svg>
                {data.label || 'Group'}
            </div>
        </div>
    );
};

export default memo(GroupNode);
