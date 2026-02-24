import { useRef } from "react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useChatRuntime } from "@assistant-ui/react-ai-sdk";
import { Thread } from "@assistant-ui/react-ui";
import "@assistant-ui/react-ui/styles/index.css";
import { LineChartTool, BarChartTool, TableTool } from "./components/tools";

const SERVER_URL = process.env.REACT_APP_SERVER_URL || "http://localhost:8000";

function App() {
  // Stable thread_id ties all requests in this session to a single LangGraph
  // checkpoint thread, enabling multi-turn conversation. Without it, every
  // request would start a fresh conversation with no memory of prior turns.
  // Resets on page refresh (new conversation), which is appropriate for a prototype.
  const threadId = useRef(crypto.randomUUID());

  const runtime = useChatRuntime({
    api: `${SERVER_URL}/api/chat`,
    body: { thread_id: threadId.current },
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
