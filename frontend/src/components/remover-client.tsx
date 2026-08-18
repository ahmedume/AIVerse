// src/components/remover-client.tsx — 1-7 humanizer with live rewrite + export.

"use client";

import { useRef, useState } from "react";

import { downloadExport, streamSSE, type Source } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SourcePicker } from "@/components/source-picker";

type Rewritten = { index: number; text: string };
type BlockStream = { index: number; type: string; text: string };

const LEVELS = [
  { v: 1, label: "Casual" },
  { v: 4, label: "Balanced" },
  { v: 7, label: "Corporate" },
];

export function RemoverClient() {
  const [source, setSource] = useState<Source>({});
  const [level, setLevel] = useState(4);
  const [running, setRunning] = useState(false);
  const [blocks, setBlocks] = useState<BlockStream[]>([]);
  const [done, setDone] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  const run = async () => {
    if (!source.text && !source.file_id) return;
    abortRef.current?.abort();
    setRunning(true);
    setDone(false);
    setBlocks([]);
    setError("");
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      await streamSSE(
        "/api/humanize",
        { source, level },
        (ev) => {
          if (ev.event === "block_start") {
            setBlocks((b) => [...b, { index: Number(ev.data.index), type: String(ev.data.type), text: "" }]);
          } else if (ev.event === "token") {
            const i = Number(ev.data.index);
            const token = String(ev.data.token);
            setBlocks((b) => b.map((blk) => (blk.index === i ? { ...blk, text: blk.text + token } : blk)));
          } else if (ev.event === "done") {
            setDone(true);
          }
        },
        ac.signal,
      );
    } catch (e) {
      if (!ac.signal.aborted) setError(e instanceof Error ? e.message : "Humanizing failed");
    } finally {
      setRunning(false);
    }
  };

  const exportDoc = async (format: "docx" | "pdf") => {
    if (!done) return;
    setExporting(true);
    try {
      await downloadExport(source, format);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  };

  const ready = Boolean(source.text || source.file_id);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Source</CardTitle>
        </CardHeader>
        <CardContent>
          <SourcePicker source={source} onChange={setSource} disabled={running} />
          <div className="mt-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-medium">
                Level {level}
                <span className="ml-2 text-xs text-muted-foreground">
                  {LEVELS.find((l) => l.v === level)?.label ??
                    (level < 3 ? "Natural" : level > 5 ? "Formal" : "Balanced")}
                </span>
              </span>
              <span className="text-xs text-muted-foreground">
                {level <= 2 ? "aggressive humanizing" : level <= 5 ? "balanced" : "corporate polish"}
              </span>
            </div>
            <input
              type="range"
              min={1}
              max={7}
              value={level}
              disabled={running}
              onChange={(e) => setLevel(Number(e.target.value))}
              className="w-full accent-foreground"
            />
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button onClick={() => void run()} disabled={!ready || running}>
              {running ? "Humanizing…" : "Humanize"}
            </Button>
            {done && (
              <>
                <Button variant="secondary" size="sm" onClick={() => void exportDoc("docx")} disabled={exporting}>
                  {exporting ? "Exporting…" : "Export DOCX"}
                </Button>
                <Button variant="secondary" size="sm" onClick={() => void exportDoc("pdf")} disabled={exporting}>
                  Export PDF
                </Button>
              </>
            )}
          </div>
          {error && <p className="mt-3 text-xs text-destructive">{error}</p>}
        </CardContent>
      </Card>

      {blocks.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Rewritten text</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {blocks.map((b) => (
              <div key={b.index}>
                {b.type === "heading" && (
                  <h4 className="font-semibold">{b.text || "…"}</h4>
                )}
                {b.type === "blockquote" && (
                  <blockquote className="border-l-2 pl-3 italic">{b.text || "…"}</blockquote>
                )}
                {b.type !== "heading" && b.type !== "blockquote" && (
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">{b.text || "…"}</p>
                )}
              </div>
            ))}
            {!done && running && (
              <p className="text-xs text-muted-foreground animate-pulse">Streaming…</p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}