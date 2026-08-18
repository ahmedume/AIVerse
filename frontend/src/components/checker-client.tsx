// src/components/checker-client.tsx — AI detection + plagiarism scan results.

"use client";

import { useRef, useState } from "react";
import { SourcePicker } from "@/components/source-picker";
import { Badge, verdictBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { type BlockScore, type FragmentResult, type Source, streamSSE } from "@/lib/api";

type Stage = "idle" | "detecting" | "scanning";

export function CheckerClient() {
  const [source, setSource] = useState<Source>({});
  const [stage, setStage] = useState<Stage>("idle");
  const [scores, setScores] = useState<BlockScore[]>([]);
  const [overall, setOverall] = useState(0);
  const [flagged, setFlagged] = useState(false);
  const [fragments, setFragments] = useState<FragmentResult[]>([]);
  const [plagChecked, setPlagChecked] = useState(0);
  const [plagMatched, setPlagMatched] = useState(0);
  const [plagTotal, setPlagTotal] = useState(0);
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  const stop = () => abortRef.current?.abort();

  const runDetect = async () => {
    if (!source.text && !source.file_id) return;
    stop();
    setStage("detecting");
    setScores([]);
    setError("");
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      await streamSSE(
        "/api/detect",
        { source },
        (ev) => {
          if (ev.event === "block_score") setScores((s) => [...s, ev.data as BlockScore]);
          if (ev.event === "done") {
            setOverall(Number(ev.data.overall ?? 0));
            setFlagged(Boolean(ev.data.flagged));
          }
        },
        ac.signal,
      );
    } catch (e) {
      if (!ac.signal.aborted) setError(e instanceof Error ? e.message : "Detection failed");
    } finally {
      setStage("idle");
    }
  };

  const runPlagiarism = async () => {
    if (!source.text && !source.file_id) return;
    stop();
    setStage("scanning");
    setFragments([]);
    setError("");
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      await streamSSE(
        "/api/plagiarism",
        { source, max_results: 5 },
        (ev) => {
          if (ev.event === "fragment") setFragments((f) => [...f, ev.data as FragmentResult]);
          if (ev.event === "done") {
            setPlagChecked(Number(ev.data.checked ?? 0));
            setPlagMatched(Number(ev.data.matched ?? 0));
            setPlagTotal(Number(ev.data.total_fragments ?? 0));
          }
        },
        ac.signal,
      );
    } catch (e) {
      if (!ac.signal.aborted) setError(e instanceof Error ? e.message : "Scan failed");
    } finally {
      setStage("idle");
    }
  };

  const busy = stage !== "idle";
  const ready = Boolean(source.text || source.file_id);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Source</CardTitle>
        </CardHeader>
        <CardContent>
          <SourcePicker source={source} onChange={setSource} disabled={busy} />
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button onClick={() => void runDetect()} disabled={!ready || busy}>
              {stage === "detecting" ? "Detecting…" : "Run AI detection"}
            </Button>
            <Button
              variant="secondary"
              onClick={() => void runPlagiarism()}
              disabled={!ready || busy}
            >
              {stage === "scanning" ? "Scanning web…" : "Check plagiarism"}
            </Button>
            {busy && (
              <Button variant="ghost" size="sm" onClick={stop}>
                Stop
              </Button>
            )}
          </div>
          {error && <p className="mt-3 text-xs text-destructive">{error}</p>}
        </CardContent>
      </Card>

      {scores.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>AI detection</span>
              <span className="flex items-center gap-2 text-sm font-normal">
                Overall {overall}/100
                <Badge variant={flagged ? "danger" : "success"}>
                  {flagged ? "Flagged" : "Likely human"}
                </Badge>
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {scores.map((s) => {
              const vb = verdictBadge(s.ai_score);
              return (
                <div key={s.index}>
                  <div className="mb-1 flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">#{s.index + 1}</span>
                      {s.ai_score.toFixed(1)}/100
                      <Badge variant={vb.variant}>{vb.label}</Badge>
                    </span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                    <div className={cnBar(s.ai_score)} style={{ width: `${s.ai_score}%` }} />
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{s.reason}</p>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {fragments.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>Plagiarism scan</span>
              <span className="text-sm font-normal text-muted-foreground">
                {plagChecked}/{plagTotal} checked · {plagMatched} matched
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {fragments.map((f) => (
              <div key={f.index} className="rounded-md border p-3">
                <p className="mb-2 text-xs text-muted-foreground">
                  Fragment #{f.index + 1}
                  {!f.checked && " — could not reach the web, skipped"}
                  {f.checked && !f.matched && " — no matches found"}
                </p>
                {f.matches.map((m) => (
                  <a
                    key={m.url}
                    href={m.url}
                    target="_blank"
                    rel="noreferrer"
                    className="block rounded p-2 hover:bg-accent"
                  >
                    <span className="block text-sm font-medium">{m.title}</span>
                    <span className="block truncate text-xs text-muted-foreground">{m.url}</span>
                    <span className="block text-xs text-muted-foreground">{m.snippet}</span>
                  </a>
                ))}
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function cnBar(score: number) {
  if (score >= 70) return "h-full rounded-full bg-red-600";
  if (score >= 40) return "h-full rounded-full bg-amber-500";
  return "h-full rounded-full bg-emerald-600";
}
