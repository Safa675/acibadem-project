"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Send, X, MessageCircle } from "lucide-react";
import type { ChatMessage } from "@/lib/types";
import { sendChatMessage } from "@/lib/api";

interface Props {
  patientId: string;
  activeTabLabel: string;
}

const AVATAR_SRC = "/images/j2.png";
const SESSION_KEY = "ilayChatOpen";

const SUGGESTED_PROMPTS = [
  "Summarize this patient's clinical status",
  "What are the key risk factors?",
  "Explain the latest lab trends",
  "Any medication interactions to watch?",
];

const COHORT_PROMPTS = [
  "What drives high-risk patients in this cohort?",
  "How many VaR RED patients do we have and why?",
  "Explain rating distribution vs VaR risk tiers",
  "Compare cohort profile with selected patient",
];

export default function IlayChatbot({ patientId, activeTabLabel }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [inputValue, setInputValue] = useState("");

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const previousTabRef = useRef(activeTabLabel);

  useEffect(() => {
    const stored = sessionStorage.getItem(SESSION_KEY);
    if (stored === "true") setIsOpen(true);
  }, []);

  useEffect(() => {
    sessionStorage.setItem(SESSION_KEY, String(isOpen));
  }, [isOpen]);

  useEffect(() => {
    setMessages([]);
  }, [patientId]);

  useEffect(() => {
    if (previousTabRef.current === activeTabLabel) return;
    previousTabRef.current = activeTabLabel;
    setMessages((prev) => {
      if (prev.length === 0) return prev;
      return [
        ...prev,
        {
          role: "assistant",
          content: `[Context mode changed: ${activeTabLabel}. I can answer cohort-wide, selected-patient, or compare both. If your question is ambiguous, I will ask a quick scope clarification.]`,
        },
      ];
    });
  }, [activeTabLabel]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  useEffect(() => {
    if (isOpen) inputRef.current?.focus();
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) setIsOpen(false);
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (isOpen && popupRef.current && !popupRef.current.contains(e.target as Node)) {
        const fab = document.getElementById("ilay-fab");
        if (fab && fab.contains(e.target as Node)) return;
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || !popupRef.current) return;

    const container = popupRef.current;
    const trapFocus = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;

      const focusable = Array.from(
        container.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), [href], select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      );

      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement as HTMLElement | null;

      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };

    container.addEventListener("keydown", trapFocus);
    return () => container.removeEventListener("keydown", trapFocus);
  }, [isOpen]);

  const handleSend = useCallback(
    async (text?: string) => {
      const content = (text ?? inputValue).trim();
      if (!content || isLoading) return;

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

      // Add a placeholder assistant message that will be filled token-by-token
      const placeholderMsg: ChatMessage = { role: "assistant", content: "" };
      setMessages((prev) => [...prev, placeholderMsg]);

      try {
        await sendChatMessage(
          updatedMessages,
          patientId,
          activeTabLabel,
          (token: string) => {
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last?.role === "assistant") {
              updated[updated.length - 1] = {
                ...last,
                content: last.content + token,
              };
            }
            return updated;
          });
          },
        );
      } catch {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last?.role === "assistant" && last.content === "") {
            updated[updated.length - 1] = {
              ...last,
              content: "Sorry, I encountered an error. Please try again.",
            };
          }
          return updated;
        });
      } finally {
        setIsLoading(false);
      }
    },
    [activeTabLabel, inputValue, isLoading, messages, patientId],
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const toggleOpen = () => setIsOpen((prev) => !prev);
  const canSend = inputValue.trim().length > 0 && !isLoading;
  const suggestedPrompts =
    activeTabLabel === "Cohort Overview" ? COHORT_PROMPTS : SUGGESTED_PROMPTS;

  return (
    <>
      {isOpen && (
        <div ref={popupRef} className="ilay-window" role="dialog" aria-label="Ilay clinical assistant">
          <div className="ilay-header">
            <img src={AVATAR_SRC} alt="Ilay avatar" className="ilay-header-avatar" />
            <div className="ilay-header-copy">
              <div className="ilay-header-title">Ilay &mdash; Patient #{patientId}</div>
              <div className="ilay-header-subtitle">AI Clinical Assistant · {activeTabLabel}</div>
            </div>
            <button onClick={() => setIsOpen(false)} aria-label="Close chat" className="ilay-close">
              <X size={20} />
            </button>
          </div>

          <div className="ilay-messages">
            {messages.length === 0 && !isLoading ? (
              <div className="ilay-welcome">
                <img src={AVATAR_SRC} alt="Ilay" className="ilay-welcome-avatar" />
                <div className="ilay-welcome-title">Merhaba! I&apos;m Ilay</div>
                <div className="ilay-welcome-subtitle">
                  Your AI clinical assistant. Ask cohort-level questions, patient-level questions, or comparisons.
                </div>
                <div className="ilay-suggestions">
                  {suggestedPrompts.map((prompt) => (
                    <button key={prompt} onClick={() => handleSend(prompt)} className="ilay-suggestion" type="button">
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <>
                {messages.map((msg, i) =>
                  msg.role === "user" ? (
                    <div key={i} className="ilay-msg-user">
                      {msg.content}
                    </div>
                  ) : (
                    <div key={i} className="ilay-msg-bot-row">
                      <img src={AVATAR_SRC} alt="" className="ilay-msg-avatar" />
                      <div className="ilay-msg-bot">{msg.content}</div>
                    </div>
                  ),
                )}

                {isLoading && messages[messages.length - 1]?.content === "" && (
                  <div className="ilay-msg-bot-row">
                    <img src={AVATAR_SRC} alt="" className="ilay-msg-avatar" />
                    <div className="ilay-typing">
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

          <div className="ilay-input-area">
            <div className="ilay-input-row">
              <input
                ref={inputRef}
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  activeTabLabel === "Cohort Overview"
                    ? "Ask about cohort risk patterns or compare with selected patient..."
                    : "Ask about the selected patient or compare with cohort..."
                }
                disabled={isLoading}
                className="ilay-input"
              />
              <button
                onClick={() => handleSend()}
                disabled={!canSend}
                aria-label="Send message"
                className={`ilay-send ${canSend ? "is-ready" : ""}`}
              >
                <Send size={18} />
              </button>
            </div>
            <div className="ilay-hint">/clear to reset</div>
          </div>
        </div>
      )}

      <button
        id="ilay-fab"
        type="button"
        aria-label={isOpen ? "Close Ilay chat" : "Open Ilay chat"}
        onClick={toggleOpen}
        className={`ilay-fab ${isOpen ? "is-open" : ""}`}
      >
        {isOpen ? <MessageCircle size={32} color="#63b6ff" /> : <img src={AVATAR_SRC} alt="Open Ilay chat" className="ilay-fab-avatar" />}
      </button>
    </>
  );
}
