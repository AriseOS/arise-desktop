/**
 * TablePreview Component
 *
 * DS-11: Displays CSV/Excel file preview as a table.
 * Shows first N rows with a "more rows" indicator.
 */

import React from 'react';
import './TablePreview.css';

function TablePreview({ headers, rows, totalRows }) {
  if (!rows || rows.length === 0) {
    return (
      <div className="table-preview-empty">
        No data to preview
      </div>
    );
  }

  // Use first row as headers if not provided separately
  const displayHeaders = headers || (rows.length > 0 ? rows[0] : []);
  const displayRows = headers ? rows : rows.slice(1);
  const remainingRows = totalRows ? totalRows - displayRows.length : 0;

  return (
    <div className="table-preview">
      <div className="table-preview-wrapper">
        <table>
          <thead>
            <tr>
              {displayHeaders.map((header, i) => (
                <th key={i} title={header}>
                  {truncateCell(header, 30)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayRows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex} title={cell}>
                    {truncateCell(cell, 50)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {remainingRows > 0 && (
        <div className="table-preview-footer">
          ... {remainingRows} more rows
        </div>
      )}
    </div>
  );
}

// Truncate cell content if too long
function truncateCell(value, maxLength = 50) {
  if (!value) return '';
  const str = String(value);
  if (str.length <= maxLength) return str;
  return str.substring(0, maxLength) + '...';
}

export default TablePreview;
