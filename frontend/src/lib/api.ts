// src/lib/api.ts — backend client: uploads, files, SSE streams, export.

export type Source = { text?: string; file_id?: string };

export type FileOut = {
  id: string;
  filename: string;
  size: number;
  blocks: number;
  words: number;
  created_at: number;
};

export type BlockScore = {
  index: number;
  ai_score: number;
  reason: string;
};

export type MatchResult = {
  title: string;
  url: string;
  snippet: string;
};

export type FragmentResult = {
  index: number;
  checked: boolean;
  matched: boolean;
  total_results: number;
  matches: MatchResult[];
};

export type SourceItem = {
  excerpt: string;
  block_index: number;
  score?: number;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export async function uploadFile(file: File): Promise<FileOut> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API}/api/files`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Upload failed (${res.status})`);
  const payload = await res.json();
  return payload.data;
}

export async function listFiles(): Promise<FileOut[]> {
  const res = await fetch(`${API}/api/files`);
  if (!res.ok) throw new Error("Could not load files");
  return (await res.json()).data;
}

export async function deleteFile(id: string): Promise<void> {
  await fetch(`${API}/api/files/${id}`, { method: "DELETE" });
}

export type SSEEvent = { event: string; data: Record<string, unknown> };

export async function streamSSE(
  path: string,
  body: unknown,
  onEvent: (ev: SSEEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`Request failed (${res.status})`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx = buffer.indexOf("\n\n");
    while (idx !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of frame.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        onEvent(JSON.parse(line.slice(6)) as SSEEvent);
      }
      idx = buffer.indexOf("\n\n");
    }
  }
}

export async function downloadExport(source: Source, format: "docx" | "pdf"): Promise<void> {
  const res = await fetch(`${API}/api/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, format }),
  });
  if (!res.ok) throw new Error(`Export failed (${res.status})`);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = `aiverse-rewrite.${format}`;
  a.click();
  URL.revokeObjectURL(url);
}
