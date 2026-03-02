"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Send, X, MessageCircle } from "lucide-react";
import type { ChatMessage } from "@/lib/types";
import { sendChatMessage } from "@/lib/api";

interface Props {
  patientId: number;
}

const AVATAR_SRC = "/images/ilay_avatar_cropped.png";
const SESSION_KEY = "ilayChatOpen";

const SUGGESTED_PROMPTS = [
  "Summarize this patient's clinical status",
  "What are the key risk factors?",
  "Explain the latest lab trends",
  "Any medication interactions to watch?",
];

export default function IlayChatbot({ patientId }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [inputValue, setInputValue] = useState("");

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Restore open state from sessionStorage on mount
  useEffect(() => {
    const stored = sessionStorage.getItem(SESSION_KEY);
    if (stored === "true") setIsOpen(true);
  }, []);

  // Persist open state
  useEffect(() => {
    sessionStorage.setItem(SESSION_KEY, String(isOpen));
  }, [isOpen]);

  // Clear messages when patientId changes
  useEffect(() => {
    setMessages([]);
  }, [patientId]);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // Focus input when popup opens
  useEffect(() => {
    if (isOpen) inputRef.current?.focus();
  }, [isOpen]);

  // Escape key closes popup
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) setIsOpen(false);
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  // Click outside closes popup
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        isOpen &&
        popupRef.current &&
        !popupRef.current.contains(e.target as Node)
      ) {
        // Don't close if clicking the FAB itself (it toggles)
        const fab = document.getElementById("ilay-fab");
        if (fab && fab.contains(e.target as Node)) return;
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen]);

  const handleSend = useCallback(
    async (text?: string) => {
      const content = (text ?? inputValue).trim();
      if (!content || isLoading) return;

      // Handle /clear command
      if (content.toLowerCase() === "/clear") {
        setMessages([]);
        setInputValue("");
        return;
      }

      const userMsg: ChatMessage = { role: "user", content };
      const updatedMessages = [...messages, userMsg];
      setMessages(updatedMessages);
      setInputValue("");
      setIsLoading(true);

      try {
        const { reply } = await sendChatMessage(updatedMessages, patientId);
        const assistantMsg: ChatMessage = { role: "assistant", content: reply };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch {
        const errorMsg: ChatMessage = {
          role: "assistant",
          content: "Sorry, I encountered an error. Please try again.",
        };
        setMessages((prev) => [...prev, errorMsg]);
      } finally {
        setIsLoading(false);
      }
    },
    [inputValue, isLoading, messages, patientId],
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const toggleOpen = () => setIsOpen((prev) => !prev);

  const handleFabKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      toggleOpen();
    }
  };

  return (
    <>
      {/* ---------- Inline styles ---------- */}
      <style>{`
        .ilay-float-btn {
          animation: ilay-pulse 2.2s ease-in-out infinite;
        }
        @keyframes ilay-pulse {
          0%, 100% { box-shadow: 0 0 0 0 rgba(99,182,255,0.45), 0 4px 24px rgba(0,0,0,0.35); }
          50%       { box-shadow: 0 0 0 12px rgba(99,182,255,0), 0 4px 32px rgba(0,0,0,0.45); }
        }
        .ilay-typing-dot {
          display: inline-block;
          width: 7px;
          height: 7px;
          border-radius: 50%;
          background: #93b3d4;
          margin: 0 2.5px;
          animation: ilay-bounce 1.3s ease-in-out infinite;
        }
        .ilay-typing-dot:nth-child(2) { animation-delay: 0.15s; }
        .ilay-typing-dot:nth-child(3) { animation-delay: 0.3s; }
        @keyframes ilay-bounce {
          0%, 80%, 100% { transform: translateY(0); }
          40%            { transform: translateY(-7px); }
        }
      `}</style>

      {/* ---------- Chat Popup ---------- */}
      {isOpen && (
        <div
          ref={popupRef}
          style={{
            position: "fixed",
            bottom: 104,
            right: 22,
            width: "calc(100vw - 44px)",
            maxWidth: 420,
            maxHeight: "min(70vh, 560px)",
            display: "flex",
            flexDirection: "column",
            background: "rgba(26,29,39,0.92)",
            backdropFilter: "blur(28px)",
            WebkitBackdropFilter: "blur(28px)",
            borderRadius: 22,
            border: "1px solid rgba(99,182,255,0.13)",
            boxShadow:
              "0 0 40px rgba(99,182,255,0.10), 0 8px 32px rgba(0,0,0,0.45)",
            zIndex: 9999,
            overflow: "hidden",
            fontFamily:
              "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
          }}
        >
          {/* ---- Header ---- */}
          <div
            style={{
              background:
                "linear-gradient(135deg, rgba(55,90,145,0.85) 0%, rgba(30,42,68,0.95) 100%)",
              padding: "14px 18px",
              display: "flex",
              alignItems: "center",
              gap: 12,
              borderBottom: "1px solid rgba(99,182,255,0.10)",
              flexShrink: 0,
            }}
          >
            <img
              src={AVATAR_SRC}
              alt="Ilay avatar"
              style={{
                width: 38,
                height: 38,
                borderRadius: "50%",
                border: "2px solid rgba(99,182,255,0.35)",
                objectFit: "cover",
              }}
            />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  color: "#e8edf4",
                  fontWeight: 600,
                  fontSize: 15,
                  lineHeight: 1.2,
                }}
              >
                Ilay &mdash; Patient #{patientId}
              </div>
              <div
                style={{
                  color: "rgba(147,179,212,0.85)",
                  fontSize: 12,
                  marginTop: 1,
                }}
              >
                AI Clinical Assistant
              </div>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              aria-label="Close chat"
              style={{
                background: "none",
                border: "none",
                color: "rgba(147,179,212,0.7)",
                cursor: "pointer",
                padding: 4,
                display: "flex",
                borderRadius: 8,
              }}
            >
              <X size={20} />
            </button>
          </div>

          {/* ---- Messages Area ---- */}
          <div
            style={{
              flex: 1,
              overflowY: "auto",
              padding: "16px 14px 8px",
              display: "flex",
              flexDirection: "column",
              gap: 10,
            }}
          >
            {messages.length === 0 && !isLoading ? (
              /* ---- Welcome Screen ---- */
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 14,
                  padding: "24px 8px",
                  textAlign: "center",
                }}
              >
                <img
                  src={AVATAR_SRC}
                  alt="Ilay"
                  style={{
                    width: 72,
                    height: 72,
                    borderRadius: "50%",
                    border: "2px solid rgba(99,182,255,0.25)",
                    objectFit: "cover",
                  }}
                />
                <div
                  style={{
                    color: "#d4dff0",
                    fontSize: 18,
                    fontWeight: 600,
                  }}
                >
                  Merhaba! I&apos;m Ilay
                </div>
                <div
                  style={{
                    color: "rgba(147,179,212,0.7)",
                    fontSize: 13,
                    lineHeight: 1.4,
                    maxWidth: 280,
                  }}
                >
                  Your AI clinical assistant. Ask me anything about this
                  patient&apos;s data.
                </div>
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 7,
                    width: "100%",
                    maxWidth: 320,
                    marginTop: 6,
                  }}
                >
                  {SUGGESTED_PROMPTS.map((prompt) => (
                    <button
                      key={prompt}
                      onClick={() => handleSend(prompt)}
                      style={{
                        background: "rgba(99,182,255,0.07)",
                        border: "1px solid rgba(99,182,255,0.15)",
                        borderRadius: 12,
                        color: "#a8c4e0",
                        fontSize: 13,
                        padding: "9px 14px",
                        cursor: "pointer",
                        textAlign: "left",
                        transition: "background 0.15s, border-color 0.15s",
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background =
                          "rgba(99,182,255,0.14)";
                        e.currentTarget.style.borderColor =
                          "rgba(99,182,255,0.30)";
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background =
                          "rgba(99,182,255,0.07)";
                        e.currentTarget.style.borderColor =
                          "rgba(99,182,255,0.15)";
                      }}
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              /* ---- Message Bubbles ---- */
              <>
                {messages.map((msg, i) =>
                  msg.role === "user" ? (
                    <div
                      key={i}
                      style={{
                        alignSelf: "flex-end",
                        maxWidth: "82%",
                        background: "rgba(40,48,68,0.65)",
                        border: "1px solid rgba(99,182,255,0.22)",
                        borderRadius: "16px 16px 4px 16px",
                        padding: "10px 14px",
                        color: "#d4dff0",
                        fontSize: 14,
                        lineHeight: 1.45,
                        wordBreak: "break-word",
                      }}
                    >
                      {msg.content}
                    </div>
                  ) : (
                    <div
                      key={i}
                      style={{
                        alignSelf: "flex-start",
                        maxWidth: "82%",
                        display: "flex",
                        gap: 8,
                        alignItems: "flex-start",
                      }}
                    >
                      <img
                        src={AVATAR_SRC}
                        alt=""
                        style={{
                          width: 24,
                          height: 24,
                          borderRadius: "50%",
                          marginTop: 2,
                          flexShrink: 0,
                          objectFit: "cover",
                        }}
                      />
                      <div
                        style={{
                          background: "rgba(36,42,58,0.55)",
                          border: "1px solid rgba(147,179,212,0.12)",
                          borderRadius: "16px 16px 16px 4px",
                          padding: "10px 14px",
                          color: "#c5d4e8",
                          fontSize: 14,
                          lineHeight: 1.5,
                          wordBreak: "break-word",
                          whiteSpace: "pre-wrap",
                        }}
                      >
                        {msg.content}
                      </div>
                    </div>
                  ),
                )}

                {/* ---- Typing Indicator ---- */}
                {isLoading && (
                  <div
                    style={{
                      alignSelf: "flex-start",
                      display: "flex",
                      gap: 8,
                      alignItems: "flex-start",
                    }}
                  >
                    <img
                      src={AVATAR_SRC}
                      alt=""
                      style={{
                        width: 24,
                        height: 24,
                        borderRadius: "50%",
                        marginTop: 2,
                        flexShrink: 0,
                        objectFit: "cover",
                      }}
                    />
                    <div
                      style={{
                        background: "rgba(36,42,58,0.55)",
                        border: "1px solid rgba(147,179,212,0.12)",
                        borderRadius: "16px 16px 16px 4px",
                        padding: "12px 16px",
                        display: "flex",
                        alignItems: "center",
                        gap: 1,
                      }}
                    >
                      <span className="ilay-typing-dot" />
                      <span className="ilay-typing-dot" />
                      <span className="ilay-typing-dot" />
                    </div>
                  </div>
                )}
              </>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* ---- Input Area ---- */}
          <div
            style={{
              padding: "10px 14px 8px",
              borderTop: "1px solid rgba(99,182,255,0.08)",
              background: "rgba(22,25,34,0.6)",
              borderRadius: "0 0 22px 22px",
              flexShrink: 0,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <input
                ref={inputRef}
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask Ilay about this patient..."
                disabled={isLoading}
                style={{
                  flex: 1,
                  background: "rgba(40,48,68,0.45)",
                  border: "1px solid rgba(99,182,255,0.10)",
                  borderRadius: 12,
                  padding: "10px 14px",
                  color: "#d4dff0",
                  fontSize: 14,
                  outline: "none",
                  fontFamily: "inherit",
                }}
              />
              <button
                onClick={() => handleSend()}
                disabled={!inputValue.trim() || isLoading}
                aria-label="Send message"
                style={{
                  background:
                    inputValue.trim() && !isLoading
                      ? "rgba(99,182,255,0.18)"
                      : "rgba(60,70,90,0.3)",
                  border: "1px solid rgba(99,182,255,0.15)",
                  borderRadius: 12,
                  width: 40,
                  height: 40,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  cursor:
                    inputValue.trim() && !isLoading
                      ? "pointer"
                      : "not-allowed",
                  color:
                    inputValue.trim() && !isLoading
                      ? "#63b6ff"
                      : "rgba(147,179,212,0.35)",
                  flexShrink: 0,
                  transition: "background 0.15s, color 0.15s",
                }}
              >
                <Send size={18} />
              </button>
            </div>
            <div
              style={{
                textAlign: "center",
                color: "rgba(147,179,212,0.35)",
                fontSize: 11,
                marginTop: 6,
                marginBottom: 2,
              }}
            >
              /clear to reset
            </div>
          </div>
        </div>
      )}

      {/* ---------- Floating Action Button ---------- */}
      <div
        id="ilay-fab"
        role="button"
        tabIndex={0}
        aria-label={isOpen ? "Close Ilay chat" : "Open Ilay chat"}
        onClick={toggleOpen}
        onKeyDown={handleFabKeyDown}
        className="ilay-float-btn"
        style={{
          position: "fixed",
          bottom: 22,
          right: 22,
          width: 72,
          height: 72,
          borderRadius: "50%",
          cursor: "pointer",
          zIndex: 10000,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          border: "2.5px solid rgba(255,255,255,0.85)",
          overflow: "hidden",
          background: isOpen ? "rgba(30,36,52,0.95)" : "transparent",
          transition: "background 0.2s",
          outline: "none",
        }}
      >
        {isOpen ? (
          <MessageCircle size={32} color="#63b6ff" />
        ) : (
          <img
            src={AVATAR_SRC}
            alt="Open Ilay chat"
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
            }}
          />
        )}
      </div>
    </>
  );
}
