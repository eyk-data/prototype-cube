import { makeAssistantToolUI } from "@assistant-ui/react";
import LineChartViz from "./LineChartViz";
import BarChartViz from "./BarChartViz";
import DataTableViz from "./DataTableViz";

export const LineChartTool = makeAssistantToolUI({
  toolName: "chart_line",
  render: ({ args, status }) => {
    if (status.type === "running") {
      return (
        <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4 my-3 animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-1/3 mb-3" />
          <div className="h-[300px] bg-gray-100 rounded" />
        </div>
      );
    }
    return (
      <LineChartViz
        title={args.title}
        x_axis_key={args.x_axis_key}
        y_axis_key={args.y_axis_key}
        data={args.data}
      />
    );
  },
});

export const BarChartTool = makeAssistantToolUI({
  toolName: "chart_bar",
  render: ({ args, status }) => {
    if (status.type === "running") {
      return (
        <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4 my-3 animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-1/3 mb-3" />
          <div className="h-[300px] bg-gray-100 rounded" />
        </div>
      );
    }
    return (
      <BarChartViz
        title={args.title}
        category_key={args.category_key}
        value_key={args.value_key}
        data={args.data}
      />
    );
  },
});

export const TableTool = makeAssistantToolUI({
  toolName: "table",
  render: ({ args, status }) => {
    if (status.type === "running") {
      return (
        <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4 my-3 animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-1/3 mb-3" />
          <div className="h-32 bg-gray-100 rounded" />
        </div>
      );
    }
    return (
      <DataTableViz
        title={args.title}
        columns={args.columns}
        data={args.data}
      />
    );
  },
});
