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
  const [showHint, setShowHint] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamedText, tools]);

  useEffect(() => {
    const showTimer = setTimeout(() => setShowHint(true), 2000);
    const hideTimer = setTimeout(() => setShowHint(false), 8000);
    return () => { clearTimeout(showTimer); clearTimeout(hideTimer); };
  }, []);

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

  const mdClasses = "max-w-[85%] px-3.5 py-2.5 rounded-lg text-[13px] bg-gray-50 text-gray-700 border border-gray-200/80 prose prose-sm prose-gray leading-relaxed [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 [&_p]:mb-2 [&_ul]:mb-2 [&_ol]:mb-2 [&_li]:mb-0.5 [&_strong]:text-gray-800";

  return (
    <>
      <div className="fixed bottom-5 right-5 z-50 flex items-end gap-2">
        {/* Hint bubble */}
        {showHint && !open && (
          <div className="mb-1 animate-fade-in">
            <div className="bg-gray-900 text-white text-[12px] px-3 py-1.5 rounded-lg shadow-lg whitespace-nowrap">
              Ask the recruitment agent
            </div>
          </div>
        )}

        <button
          onClick={() => { setOpen(!open); setShowHint(false); }}
          className="relative w-14 h-14 rounded-full bg-gray-900 text-white flex items-center justify-center shadow-lg hover:bg-gray-800 transition-all cursor-pointer hover:scale-105"
          title="Chat with agent"
        >
          {open ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
          )}
          {!open && showHint && (
            <span className="absolute -top-0.5 -right-0.5 w-3 h-3 bg-[var(--redhat-red)] rounded-full animate-pulse" />
          )}
        </button>
      </div>

      {open && (
        <div className="fixed bottom-20 right-5 z-50 w-[460px] h-[620px] bg-white rounded-lg border border-gray-200/80 shadow-2xl flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
            <div>
              <p className="text-[13px] font-medium tracking-tight">Recruitment Agent</p>
              <p className="text-[11px] text-gray-400">Ask questions or run the pipeline</p>
            </div>
            <button
              onClick={resetChat}
              className="text-[11px] text-gray-400 hover:text-gray-600 px-2 py-1 rounded-md hover:bg-gray-50 transition-colors cursor-pointer"
            >
              Clear
            </button>
          </div>

          <div className="flex-1 overflow-auto px-4 py-4 space-y-4">
            {messages.length === 0 && !sending && (
              <p className="text-[13px] text-gray-400 text-center mt-12">
                Send a message to start.
              </p>
            )}

            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                {msg.role === "user" ? (
                  <div className="max-w-[85%] px-3.5 py-2 rounded-lg text-[13px] whitespace-pre-wrap bg-gray-900 text-white">
                    {msg.content}
                  </div>
                ) : (
                  <div className={mdClasses}>
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                  </div>
                )}
              </div>
            ))}

            {tools.length > 0 && (
              <div className="space-y-1 pl-1">
                {tools.map((t, i) => (
                  <div key={i} className="flex items-center gap-2 text-[11px] text-gray-400">
                    {t.done ? (
                      <svg className="w-3 h-3 text-green-500" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd"/></svg>
                    ) : (
                      <div className="w-3 h-3 border border-gray-300 border-t-gray-500 rounded-full animate-spin" />
                    )}
                    <span>{t.label}</span>
                  </div>
                ))}
              </div>
            )}

            {streamedText && (
              <div className="flex justify-start">
                <div className={mdClasses}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamedText}</ReactMarkdown>
                </div>
              </div>
            )}

            {sending && !streamedText && tools.length === 0 && (
              <div className="flex items-center gap-2 pl-1">
                <div className="w-3 h-3 border border-gray-300 border-t-gray-500 rounded-full animate-spin" />
                <span className="text-[11px] text-gray-400">Thinking...</span>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          <div className="px-3 py-3 border-t border-gray-100">
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
                className="flex-1 px-3 py-2 text-[13px] border border-gray-200 rounded-md bg-gray-50 focus:bg-white focus:outline-none focus:ring-1 focus:ring-gray-300 focus:border-gray-300 disabled:opacity-50 transition-colors"
              />
              <button
                type="submit"
                disabled={sending || !input.trim()}
                className="px-3.5 py-2 text-[13px] font-medium text-white bg-gray-900 rounded-md hover:bg-gray-800 disabled:opacity-30 transition-colors cursor-pointer"
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
