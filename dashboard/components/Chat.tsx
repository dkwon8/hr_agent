"use client";

import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API_BASE = "http://localhost:8001";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface ToolStatus {
  label: string;
  done: boolean;
}

export default function Chat() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [tools, setTools] = useState<ToolStatus[]>([]);
  const [streamedText, setStreamedText] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamedText, tools]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || sending) return;

    setInput("");
    setSending(true);
    setStreamedText("");
    setTools([]);
    setMessages((prev) => [...prev, { role: "user", content: text }]);

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });

      const reader = res.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = JSON.parse(line.slice(6));

          if (data.type === "text") {
            setStreamedText((prev) => prev + data.content);
          } else if (data.type === "tool_start") {
            setTools((prev) => [...prev, { label: data.tool, done: false }]);
          } else if (data.type === "tool_done") {
            setTools((prev) => {
              const updated = [...prev];
              const last = updated.findLastIndex((t) => !t.done);
              if (last >= 0) updated[last] = { ...updated[last], done: true };
              return updated;
            });
          } else if (data.type === "done") {
            setMessages((prev) => [...prev, { role: "assistant", content: data.content }]);
            setStreamedText("");
            setTools([]);
          }
        }
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Could not reach the agent. Is the API server running?" },
      ]);
      setStreamedText("");
      setTools([]);
    }

    setSending(false);
  };

  const resetChat = async () => {
    await fetch(`${API_BASE}/api/chat/reset`, { method: "POST" }).catch(() => {});
    setMessages([]);
    setStreamedText("");
    setTools([]);
  };

  return (
    <>
      {/* Toggle button */}
      <button
        onClick={() => setOpen(!open)}
        className="fixed bottom-5 right-5 z-50 w-12 h-12 rounded-full bg-gray-900 text-white flex items-center justify-center shadow-lg hover:bg-gray-800 transition-colors cursor-pointer"
        title="Chat with agent"
      >
        {open ? (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
        ) : (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
        )}
      </button>

      {/* Chat panel */}
      {open && (
        <div className="fixed bottom-20 right-5 z-50 w-[440px] h-[600px] bg-white rounded-xl border border-gray-200 shadow-xl flex flex-col overflow-hidden">
          {/* Header */}
          <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between bg-gray-50">
            <div>
              <p className="text-sm font-medium">Recruitment Agent</p>
              <p className="text-xs text-gray-400">Ask questions or run the pipeline</p>
            </div>
            <button
              onClick={resetChat}
              className="text-xs text-gray-400 hover:text-gray-600 px-2 py-1 rounded hover:bg-gray-100 transition-colors cursor-pointer"
            >
              Clear
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-auto p-4 space-y-4">
            {messages.length === 0 && !sending && (
              <p className="text-sm text-gray-400 text-center mt-8">
                Send a message to start.
              </p>
            )}

            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                {msg.role === "user" ? (
                  <div className="max-w-[85%] px-3 py-2 rounded-lg text-sm whitespace-pre-wrap bg-gray-900 text-white">
                    {msg.content}
                  </div>
                ) : (
                  <div className="max-w-[85%] px-3 py-2 rounded-lg text-sm bg-gray-100 text-gray-800 border border-gray-200 prose prose-sm prose-gray leading-relaxed [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 [&_p]:mb-2 [&_ul]:mb-2 [&_li]:mb-0.5">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                  </div>
                )}
              </div>
            ))}

            {/* Tool progress */}
            {tools.length > 0 && (
              <div className="space-y-1">
                {tools.map((t, i) => (
                  <p key={i} className="text-xs text-gray-500">
                    {t.done ? "✓" : "•"} {t.label}
                  </p>
                ))}
              </div>
            )}

            {/* Streaming text */}
            {streamedText && (
              <div className="flex justify-start">
                <div className="max-w-[85%] px-3 py-2 rounded-lg text-sm bg-gray-100 text-gray-800 border border-gray-200 prose prose-sm prose-gray leading-relaxed [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 [&_p]:mb-2 [&_ul]:mb-2 [&_li]:mb-0.5">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamedText}</ReactMarkdown>
                </div>
              </div>
            )}

            {sending && !streamedText && tools.length === 0 && (
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
                <span className="text-xs text-gray-400">Thinking...</span>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="p-3 border-t border-gray-200">
            <form
              onSubmit={(e) => { e.preventDefault(); sendMessage(); }}
              className="flex gap-2"
            >
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask the agent..."
                disabled={sending}
                className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-gray-300 disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={sending || !input.trim()}
                className="px-3 py-2 text-sm font-medium text-white bg-gray-900 rounded-lg hover:bg-gray-800 disabled:opacity-40 transition-colors cursor-pointer"
              >
                Send
              </button>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
