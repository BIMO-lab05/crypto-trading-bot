import React from 'react'
import PropTypes from 'prop-types'

/**
 * ChartFigure - accessibility wrapper for charts.
 *
 * Wraps the chart in <figure role="img" aria-label> so screen readers
 * announce the high-level summary instead of "graphic" or nothing.
 * Below the chart, renders a collapsible <details> with a summary
 * table providing the same data in a non-visual form (WCAG 1.1.1).
 *
 * Pass `summary` (string) as the announced description, and optional
 * `tableCaption`, `columns`, `rows` for the text-table fallback.
 *
 * @param {object} props
 * @param {string} props.summary - announced text alternative for the chart
 * @param {string} [props.tableCaption] - caption for the <details> table
 * @param {Array<{key: string, label: string}>} [props.columns]
 * @param {Array<object>} [props.rows] - rows of {[col.key]: value}
 * @param {string} [props.className]
 * @param {React.ReactNode} props.children - the chart itself
 */
export default function ChartFigure({
  summary,
  tableCaption,
  columns,
  rows,
  className = '',
  children,
}) {
  const hasTable = Array.isArray(columns) && columns.length > 0 && Array.isArray(rows) && rows.length > 0

  return (
    <figure role="img" aria-label={summary} className={`m-0 ${className}`}>
      {children}
      {hasTable && (
        <details className="mt-2">
          <summary className="cursor-pointer select-none text-xs text-slate-500 hover:text-slate-300 transition-colors px-2 py-1">
            View data as table
          </summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-xs text-slate-300 border-collapse">
              {tableCaption && <caption className="sr-only">{tableCaption}</caption>}
              <thead>
                <tr>
                  {columns.map((col) => (
                    <th
                      key={col.key}
                      scope="col"
                      className="text-left p-2 border-b border-slate-700 font-semibold text-slate-200"
                    >
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={row.__key ?? i}>
                    {columns.map((col) => (
                      <td
                        key={col.key}
                        className="p-2 border-b border-slate-800/60"
                      >
                        {row[col.key] ?? ''}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </figure>
  )
}

ChartFigure.propTypes = {
  summary: PropTypes.string.isRequired,
  tableCaption: PropTypes.string,
  columns: PropTypes.arrayOf(
    PropTypes.shape({
      key: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired,
    }),
  ),
  rows: PropTypes.array,
  className: PropTypes.string,
  children: PropTypes.node,
}
