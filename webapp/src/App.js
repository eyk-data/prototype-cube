import { useState, useEffect, useCallback } from "react";
import "@assistant-ui/react-ui/styles/index.css";
import ChatView from "./ChatView";
import Sidebar from "./Sidebar";

const SERVER_URL = process.env.REACT_APP_SERVER_URL || "http://localhost:8000";

function App() {
  const [chats, setChats] = useState([]);
  const [activeThreadId, setActiveThreadId] = useState(crypto.randomUUID());
  const [initialMessages, setInitialMessages] = useState([]);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const fetchChats = useCallback(async () => {
    try {
      const res = await fetch(`${SERVER_URL}/api/chats/`);
      if (res.ok) {
        setChats(await res.json());
      }
    } catch (err) {
      console.error("Failed to fetch chats:", err);
    }
  }, []);

  useEffect(() => {
    fetchChats();
  }, [fetchChats]);

  const handleSelectChat = async (threadId) => {
    try {
      const res = await fetch(`${SERVER_URL}/api/chats/${threadId}/messages`);
      if (res.ok) {
        const messages = await res.json();
        setInitialMessages(messages);
        setActiveThreadId(threadId);
      }
    } catch (err) {
      console.error("Failed to fetch messages:", err);
    }
  };

  const handleNewChat = () => {
    setActiveThreadId(crypto.randomUUID());
    setInitialMessages([]);
  };

  const handleMessageSent = () => {
    fetchChats();
  };

  return (
    <div className="flex h-screen">
      <Sidebar
        chats={chats}
        activeThreadId={activeThreadId}
        onSelectChat={handleSelectChat}
        onNewChat={handleNewChat}
        collapsed={sidebarCollapsed}
      />
      <div className="flex flex-col flex-1 min-w-0">
        <header className="border-b px-4 py-3 flex items-center gap-3">
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className="text-gray-500 hover:text-gray-700"
            aria-label="Toggle sidebar"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 6h16M4 12h16M4 18h16"
              />
            </svg>
          </button>
          <h1 className="text-lg font-semibold">Eyk AI Assistant</h1>
        </header>
        <div className="flex-1 overflow-hidden">
          <ChatView
            key={activeThreadId}
            threadId={activeThreadId}
            initialMessages={initialMessages}
            onMessageSent={handleMessageSent}
          />
        </div>
      </div>
    </div>
  );
}

export default App;
