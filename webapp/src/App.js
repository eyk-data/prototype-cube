import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useChatRuntime } from "@assistant-ui/react-ai-sdk";
import { Thread } from "@assistant-ui/react-ui";
import "@assistant-ui/react-ui/styles/index.css";
import { LineChartTool, BarChartTool, TableTool } from "./components/tools";

const SERVER_URL = process.env.REACT_APP_SERVER_URL || "http://localhost:8000";

function App() {
  const runtime = useChatRuntime({
    api: `${SERVER_URL}/api/chat`,
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <LineChartTool />
      <BarChartTool />
      <TableTool />
      <div className="flex flex-col h-screen">
        <header className="border-b px-4 py-3">
          <h1 className="text-lg font-semibold">Eyk AI Assistant</h1>
        </header>
        <div className="flex-1 overflow-hidden">
          <Thread />
        </div>
      </div>
    </AssistantRuntimeProvider>
  );
}

export default App;
