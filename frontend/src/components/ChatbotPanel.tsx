import React, { useState, useRef, useEffect } from 'react';
import {
  Bot,
  User,
  Send,
  Sparkles,
  ShieldAlert,
  Loader2,
  Trash2,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import { api } from '../services/api';
import { ChatMessage, ChatbotStatus } from '../types';

export const ChatbotPanel: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      sender: 'assistant',
      text: 'Hello! I am AquaAdvisor, your AI Water Quality Consultant for HydroSense. I analyze live telemetry from your monitor, evaluate EPA/WHO standards, and track anomaly trends. How can I help you today?',
      timestamp: new Date().toLocaleTimeString(),
      source: 'system',
    },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState<ChatbotStatus | null>(null);
  const [sessionId] = useState(() => `session_${Math.random().toString(36).substring(2, 9)}`);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const suggestedQuestions = [
    'Is the water currently safe to drink?',
    'What causes high turbidity?',
    'How can I improve apartment water quality?',
    'Summarize recent ML anomaly detections and drift',
    'Why is the TDS sensor reporting null?',
  ];

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  useEffect(() => {
    api.getChatbotStatus()
      .then((s) => setStatus(s))
      .catch((err) => console.warn('Could not load chatbot status:', err));
  }, []);

  const handleSend = async (messageText: string) => {
    const textToSend = messageText.trim();
    if (!textToSend || isLoading) return;

    const userMsg: ChatMessage = {
      id: `user_${Date.now()}`,
      sender: 'user',
      text: textToSend,
      timestamp: new Date().toLocaleTimeString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    try {
      const res = await api.askChatbot(textToSend, sessionId);
      const assistantMsg: ChatMessage = {
        id: `assistant_${Date.now()}`,
        sender: 'assistant',
        text: res.response,
        timestamp: new Date().toLocaleTimeString(),
        source: res.source,
        model: res.model_used,
        provider_status: res.provider_status,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: any) {
      const errorMsg: ChatMessage = {
        id: `err_${Date.now()}`,
        sender: 'assistant',
        text: `Error contacting backend AI service: ${err.message || 'Check if FastAPI is running at http://127.0.0.1:8000'}.`,
        timestamp: new Date().toLocaleTimeString(),
        source: 'error',
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleClear = () => {
    setMessages([
      {
        id: `welcome_${Date.now()}`,
        sender: 'assistant',
        text: 'Conversation cleared. How can I assist you with your water quality monitoring?',
        timestamp: new Date().toLocaleTimeString(),
        source: 'system',
      },
    ]);
  };

  const getSourceBadge = (source?: string, model?: string | null, providerStatus?: string | null) => {
    if (!source || source === 'system') return null;

    if (source === 'gemini_llm') {
      return (
        <span className="inline-flex items-center space-x-1 text-[10px] font-semibold px-2 py-0.5 rounded bg-purple-100 text-purple-800 border border-purple-200">
          <Sparkles className="h-3 w-3 text-purple-600" />
          <span>Gemini AI ({model || 'gemini-3.1-flash-lite'})</span>
        </span>
      );
    }

    if (source === 'openai_llm') {
      return (
        <span className="inline-flex items-center space-x-1 text-[10px] font-semibold px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 border border-emerald-200">
          <Sparkles className="h-3 w-3 text-emerald-600" />
          <span>OpenAI ({model || 'gpt-4o-mini'})</span>
        </span>
      );
    }

    return (
      <span className="inline-flex items-center space-x-1 text-[10px] font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200" title={providerStatus || undefined}>
        <Bot className="h-3 w-3 text-slate-500" />
        <span>Deterministic Rule Engine</span>
      </span>
    );
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200/90 shadow-xs flex flex-col h-[650px] overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-slate-200 flex items-center justify-between bg-slate-50/50">
        <div className="flex items-center space-x-3">
          <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-sky-600 to-indigo-600 text-white flex items-center justify-center shadow-xs">
            <Bot className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="font-bold text-slate-900 text-sm">
                AI Water Advisor &amp; Assistant
              </h3>
            </div>
            <p className="text-[11px] text-slate-500">
              Evaluates live IoT telemetry, physical standards, and anomaly logs
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          {/* Provider status badge */}
          {status && (
            <div className="hidden sm:flex items-center space-x-1.5 text-xs px-2.5 py-1 rounded-full border">
              {status.status === 'ready' && status.configured_provider === 'gemini' ? (
                <span className="flex items-center space-x-1.5 text-purple-800 bg-purple-50 px-2 py-0.5 rounded-full border border-purple-200">
                  <span className="w-2 h-2 rounded-full bg-purple-600 animate-pulse" />
                  <Sparkles className="h-3 w-3 text-purple-600" />
                  <span className="font-semibold">Gemini AI Online ({status.model})</span>
                </span>
              ) : status.status === 'ready' ? (
                <span className="flex items-center space-x-1.5 text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                  <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                  <span className="font-semibold">{status.configured_provider.toUpperCase()} Online</span>
                </span>
              ) : (
                <span className="flex items-center space-x-1.5 text-slate-600 bg-slate-100 px-2 py-0.5 rounded-full border border-slate-200">
                  <AlertCircle className="h-3 w-3 text-amber-500" />
                  <span>Rule Fallback Mode</span>
                </span>
              )}
            </div>
          )}

          <button
            onClick={handleClear}
            title="Clear Chat History"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200/60 transition-colors"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Mandatory Safety Notice */}
      <div className="bg-amber-50/70 border-b border-amber-200/70 px-4 py-2 text-[11px] text-amber-900 flex items-center space-x-2">
        <ShieldAlert className="h-4 w-4 text-amber-600 shrink-0" />
        <span>
          <strong>AI Safety Notice:</strong> The advisor interprets physical parameters only. It does not certify microbiological water safety.
        </span>
      </div>

      {/* Message Stream */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg) => {
          const isUser = msg.sender === 'user';
          return (
            <div
              key={msg.id}
              className={`flex items-start space-x-3 ${isUser ? 'flex-row-reverse space-x-reverse' : ''}`}
            >
              <div
                className={`h-7 w-7 rounded-lg flex items-center justify-center shrink-0 text-xs ${
                  isUser
                    ? 'bg-sky-600 text-white shadow-2xs'
                    : 'bg-slate-100 text-slate-700 border border-slate-200'
                }`}
              >
                {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
              </div>

              <div className={`max-w-[80%] space-y-1 ${isUser ? 'text-right' : 'text-left'}`}>
                <div
                  className={`p-3.5 rounded-2xl text-xs leading-relaxed whitespace-pre-wrap ${
                    isUser
                      ? 'bg-sky-600 text-white rounded-tr-none'
                      : 'bg-slate-50 border border-slate-200/80 text-slate-800 rounded-tl-none shadow-2xs'
                  }`}
                >
                  {msg.text}
                </div>

                <div className={`flex items-center space-x-2 text-[10px] text-slate-400 px-1 ${isUser ? 'justify-end' : 'justify-start'}`}>
                  <span>{msg.timestamp}</span>
                  {!isUser && getSourceBadge(msg.source, msg.model, msg.provider_status)}
                </div>
              </div>
            </div>
          );
        })}

        {isLoading && (
          <div className="flex items-center space-x-3">
            <div className="h-7 w-7 rounded-lg bg-slate-100 text-slate-600 flex items-center justify-center">
              <Loader2 className="h-4 w-4 animate-spin text-sky-600" />
            </div>
            <div className="bg-slate-50 border border-slate-200 rounded-2xl rounded-tl-none p-3 text-xs text-slate-500 flex items-center space-x-2">
              <Sparkles className="h-3.5 w-3.5 text-purple-600 animate-spin" />
              <span>AquaAdvisor is analyzing telemetry and consulting Gemini AI...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Prompts */}
      <div className="px-4 py-2 border-t border-slate-100 bg-slate-50/50 flex items-center space-x-2 overflow-x-auto">
        <span className="text-[10px] font-semibold text-slate-400 uppercase shrink-0">
          Suggested:
        </span>
        {suggestedQuestions.map((q, i) => (
          <button
            key={i}
            onClick={() => handleSend(q)}
            disabled={isLoading}
            className="text-[11px] bg-white hover:bg-slate-100 text-slate-700 px-2.5 py-1 rounded-full border border-slate-200 whitespace-nowrap transition-colors shadow-2xs disabled:opacity-50"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Input Area */}
      <div className="p-3 border-t border-slate-200 bg-white">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend(input);
          }}
          className="flex items-center space-x-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isLoading}
            placeholder="Ask AquaAdvisor about water quality, pH drift, turbidity, or sensor hardware..."
            className="flex-1 text-xs sm:text-sm px-4 py-2.5 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-sky-500/20 focus:border-sky-500 transition-all disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="p-2.5 rounded-lg bg-sky-600 hover:bg-sky-700 text-white transition-colors disabled:opacity-40 shadow-xs"
          >
            <Send className="h-4 w-4" />
          </button>
        </form>
      </div>
    </div>
  );
};
