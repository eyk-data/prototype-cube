function formatHeader(key) {
  // Strip cube prefix (e.g. "Orders.totalRevenue" -> "Total Revenue")
  const name = key.includes(".") ? key.split(".").pop() : key;
  return name
    .replace(/([A-Z])/g, " $1")
    .replace(/_/g, " ")
    .replace(/^\w/, (c) => c.toUpperCase())
    .trim();
}

function formatCell(value) {
  if (value == null) return "-";
  // Format numbers with locale
  if (typeof value === "number") return value.toLocaleString();
  // Truncate ISO dates to date only
  if (typeof value === "string" && value.match(/^\d{4}-\d{2}-\d{2}T/)) {
    return value.slice(0, 10);
  }
  return String(value);
}

export default function DataTableViz({ title, columns, data }) {
  if (!data || data.length === 0) {
    return (
      <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4 my-3">
        <h3 className="text-sm font-semibold text-gray-700 mb-2">{title}</h3>
        <p className="text-gray-400 text-sm">No data available</p>
      </div>
    );
  }

  // Use provided columns, or fall back to keys from first row
  const cols = columns && columns.length > 0 ? columns : Object.keys(data[0]);

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4 my-3">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">{title}</h3>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200">
              {cols.map((col) => (
                <th
                  key={col}
                  className="px-3 py-2 text-left font-medium text-gray-600"
                >
                  {formatHeader(col)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => (
              <tr
                key={i}
                className={i % 2 === 0 ? "bg-white" : "bg-gray-50"}
              >
                {cols.map((col) => (
                  <td key={col} className="px-3 py-2 text-gray-800">
                    {formatCell(row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
