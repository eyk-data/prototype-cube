function timeAgo(dateStr) {
  const now = new Date();
  const date = new Date(dateStr);
  const seconds = Math.floor((now - date) / 1000);

  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}

function Sidebar({ chats, activeThreadId, onSelectChat, onNewChat, collapsed }) {
  if (collapsed) return null;

  return (
    <div className="w-64 bg-gray-50 border-r flex flex-col h-full shrink-0">
      <div className="p-3 border-b">
        <button
          onClick={onNewChat}
          className="w-full px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-100 transition-colors"
        >
          + New Chat
        </button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {chats.length === 0 ? (
          <p className="text-sm text-gray-400 p-4 text-center">
            No conversations yet
          </p>
        ) : (
          chats.map((chat) => {
            const isActive = chat.thread_id === activeThreadId;
            return (
              <button
                key={chat.thread_id}
                onClick={() => onSelectChat(chat.thread_id)}
                className={`w-full text-left px-3 py-2.5 border-b border-gray-100 hover:bg-gray-100 transition-colors ${
                  isActive
                    ? "bg-blue-50 border-l-2 border-l-blue-500"
                    : ""
                }`}
              >
                <div className="text-sm font-medium text-gray-800 truncate">
                  {chat.title}
                </div>
                <div className="text-xs text-gray-400 mt-0.5">
                  {timeAgo(chat.updated_at)}
                </div>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}

export default Sidebar;
