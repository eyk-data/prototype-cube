import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useChatRuntime } from "@assistant-ui/react-ai-sdk";
import { Thread } from "@assistant-ui/react-ui";
import { LineChartTool, BarChartTool, TableTool } from "./components/tools";

const SERVER_URL = process.env.REACT_APP_SERVER_URL || "http://localhost:8000";

function ChatView({ threadId, initialMessages, onMessageSent }) {
  const runtime = useChatRuntime({
    api: `${SERVER_URL}/api/chat`,
    body: { thread_id: threadId },
    initialMessages,
    onFinish: () => {
      if (onMessageSent) onMessageSent();
    },
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <LineChartTool />
      <BarChartTool />
      <TableTool />
      <div className="flex-1 overflow-hidden h-full">
        <Thread />
      </div>
    </AssistantRuntimeProvider>
  );
}

export default ChatView;
