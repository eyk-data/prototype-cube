import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

function formatLabel(key) {
  const name = key.includes(".") ? key.split(".").pop() : key;
  return name
    .replace(/([A-Z])/g, " $1")
    .replace(/_/g, " ")
    .replace(/^\w/, (c) => c.toUpperCase())
    .trim();
}

export default function BarChartViz({
  title,
  category_key,
  value_key,
  data,
}) {
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
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis
            dataKey={category_key}
            tick={{ fontSize: 12 }}
            tickFormatter={(v) => formatLabel(String(v))}
          />
          <YAxis tick={{ fontSize: 12 }} />
          <Tooltip />
          <Bar
            dataKey={value_key}
            fill="#6366f1"
            radius={[4, 4, 0, 0]}
            name={formatLabel(value_key)}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
