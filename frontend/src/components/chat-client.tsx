// src/components/chat-client.tsx — RAG chatbot over the selected document.

"use client";

import { useRef, useState } from "react";
import { SourcePicker } from "@/components/source-picker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { type Source, type SourceItem, streamSSE } from "@/lib/api";

type Msg = { id: number; role: "user" | "assistant"; content: string };
type Activity = { id: number; label: string };

const SUGGESTIONS = [
  "Where is the most AI-like content in this document?",
  "Summarize the key points in plain language.",
  "Which paragraphs should I rewrite to sound more human?",
];

export function ChatClient() {
  const [source, setSource] = useState<Source>({});
  const [messages, setMessages] = useState<Msg[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const msgIdRef = useRef(0);
  const activityIdRef = useRef(0);

  const scroll = () => endRef.current?.scrollIntoView({ behavior: "smooth" });

  const ask = async (q: string) => {
    const questionText = q.trim();
    if (!questionText || busy || (!source.text && !source.file_id)) return;
    abortRef.current?.abort();
    setQuestion("");
    setActivity([]);
    setSources([]);
    setError("");
    setMessages((m) => [...m, { id: ++msgIdRef.current, role: "user", content: questionText }]);
    setMessages((m) => [...m, { id: ++msgIdRef.current, role: "assistant", content: "" }]);
    setBusy(true);
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      await streamSSE(
        "/api/chat",
        { source, question: questionText },
        (ev) => {
          if (ev.event === "tool_start") {
            setActivity((a) => [
              ...a,
              { id: ++activityIdRef.current, label: `Using ${String(ev.data.name)}…` },
            ]);
          } else if (ev.event === "tool_end") {
            setActivity((a) => [
              ...a,
              { id: ++activityIdRef.current, label: `${String(ev.data.name)} done` },
            ]);
          } else if (ev.event === "token") {
            const token = String(ev.data.token);
            setMessages((m) => {
              const next = [...m];
              const last = next[next.length - 1];
              next[next.length - 1] = { ...last, content: last.content + token };
              return next;
            });
            scroll();
          } else if (ev.event === "sources") {
            setSources(ev.data.items as SourceItem[]);
          }
        },
        ac.signal,
      );
    } catch (e) {
      if (!ac.signal.aborted) setError(e instanceof Error ? e.message : "Chat failed");
    } finally {
      setBusy(false);
      scroll();
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Document</CardTitle>
        </CardHeader>
        <CardContent>
          <SourcePicker source={source} onChange={setSource} disabled={busy} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Ask about this document</span>
            {busy && (
              <span className="text-xs font-normal text-muted-foreground animate-pulse">
                Thinking…
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="mb-3 space-y-2">
            {messages.map((m, i) => (
              <div
                key={m.id}
                className={m.role === "user" ? "flex justify-end" : "flex justify-start"}
              >
                <div
                  className={
                    m.role === "user"
                      ? "max-w-[85%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground whitespace-pre-wrap"
                      : "max-w-[85%] rounded-lg bg-muted px-3 py-2 text-sm whitespace-pre-wrap"
                  }
                >
                  {m.content || (busy && i === messages.length - 1 ? "…" : "")}
                </div>
              </div>
            ))}
            {activity.map((a) => (
              <p key={a.id} className="text-xs text-muted-foreground">
                ↳ {a.label}
              </p>
            ))}
            {error && <p className="text-xs text-destructive">{error}</p>}
            <div ref={endRef} />
          </div>

          {messages.length === 0 && (
            <div className="mb-3 flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  disabled={busy}
                  onClick={() => void ask(s)}
                  className="rounded-full border px-3 py-1 text-xs hover:bg-accent disabled:opacity-50"
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          <div className="flex gap-2">
            <Textarea
              placeholder={
                source.text || source.file_id
                  ? "Ask about the document…"
                  : "Pick a source above first"
              }
              value={question}
              disabled={busy || (!source.text && !source.file_id)}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void ask(question);
                }
              }}
              className="min-h-12"
            />
            <Button onClick={() => void ask(question)} disabled={busy || !question.trim()}>
              Send
            </Button>
          </div>

          {sources.length > 0 && (
            <div className="mt-4 space-y-1.5">
              <p className="lisa-label text-muted-foreground">Sources</p>
              {sources.map((s) => (
                <div
                  key={`${s.block_index}-${s.excerpt.slice(0, 40)}`}
                  className="flex items-start gap-2 rounded border p-2 text-xs"
                >
                  <Badge variant="outline">#{s.block_index + 1}</Badge>
                  <span className="text-muted-foreground">{s.excerpt}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
