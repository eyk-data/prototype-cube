import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

function formatLabel(key) {
  // Strip cube prefix (e.g. "Orders.createdAt" -> "Created At")
  const name = key.includes(".") ? key.split(".").pop() : key;
  return name
    .replace(/([A-Z])/g, " $1")
    .replace(/_/g, " ")
    .replace(/^\w/, (c) => c.toUpperCase())
    .trim();
}

export default function LineChartViz({ title, x_axis_key, y_axis_key, data }) {
  if (!data || data.length === 0) {
    return (
      <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4 my-3">
        <h3 className="text-sm font-semibold text-gray-700 mb-2">{title}</h3>
        <p className="text-gray-400 text-sm">No data available</p>
      </div>
    );
  }

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4 my-3">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">{title}</h3>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis
            dataKey={x_axis_key}
            tick={{ fontSize: 12 }}
            tickFormatter={(v) =>
              typeof v === "string" && v.match(/^\d{4}-\d{2}/)
                ? v.slice(0, 10)
                : v
            }
          />
          <YAxis tick={{ fontSize: 12 }} />
          <Tooltip
            labelFormatter={(v) =>
              typeof v === "string" && v.match(/^\d{4}-\d{2}/)
                ? v.slice(0, 10)
                : v
            }
          />
          <Line
            type="monotone"
            dataKey={y_axis_key}
            stroke="#6366f1"
            strokeWidth={2}
            dot={{ r: 3 }}
            name={formatLabel(y_axis_key)}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
