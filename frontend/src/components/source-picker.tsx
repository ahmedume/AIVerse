// src/components/source-picker.tsx — paste text, upload a file, or reuse an uploaded file.
// Exports: SourcePicker

"use client";
import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { Textarea } from "@/components/ui/textarea";
import { deleteFile, type FileOut, listFiles, type Source, uploadFile } from "@/lib/api";
import { cn } from "@/lib/utils";

const MODES = ["text", "upload", "library"] as const;
type Mode = (typeof MODES)[number];

type Props = {
  source: Source;
  onChange: (s: Source) => void;
  disabled?: boolean;
};

export function SourcePicker({ source, onChange, disabled }: Props) {
  const [mode, setMode] = useState<Mode>(source.text ? "text" : "upload");
  const [text, setText] = useState(source.text ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const filesQuery = useQuery({ queryKey: ["files"], queryFn: listFiles });
  const files: FileOut[] = filesQuery.data ?? [];

  const pickText = (value: string) => {
    setText(value);
    onChange(value.trim() ? { text: value } : {});
  };

  const pickUpload = async (file?: File) => {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const out = await uploadFile(file);
      onChange({ file_id: out.id });
      await filesQuery.refetch();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const removeFile = async (id: string) => {
    await deleteFile(id);
    if (source.file_id === id) onChange({});
    await filesQuery.refetch();
  };

  return (
    <div className="space-y-3">
      <div className="flex gap-1 rounded-lg border border-input p-1">
        {MODES.map((m) => (
          <button
            key={m}
            type="button"
            disabled={disabled}
            onClick={() => setMode(m)}
            className={cn(
              "flex-1 rounded-md px-3 py-1.5 text-xs font-medium capitalize transition-colors",
              mode === m ? "bg-primary text-primary-foreground" : "hover:bg-accent",
            )}
          >
            {m === "library" ? "Library" : m === "upload" ? "Upload file" : "Paste text"}
          </button>
        ))}
      </div>

      {mode === "text" && (
        <Textarea
          placeholder="Paste your text here…"
          value={text}
          disabled={disabled}
          onChange={(e) => pickText(e.target.value)}
          className="min-h-36"
        />
      )}

      {mode === "upload" && (
        <div className="flex items-center gap-3">
          <input
            ref={inputRef}
            type="file"
            accept=".txt,.md,.json,.pdf,.docx"
            disabled={disabled || busy}
            className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-primary-foreground"
            onChange={(e) => void pickUpload(e.target.files?.[0])}
          />
          {busy && <span className="text-xs text-muted-foreground">Uploading…</span>}
        </div>
      )}

      {mode === "library" && (
        <ul className="divide-y rounded-md border">
          {files.length === 0 && (
            <li className="px-4 py-3 text-sm text-muted-foreground">No uploaded files yet.</li>
          )}
          {files.map((f) => (
            <li key={f.id} className="flex items-center justify-between gap-3 px-4 py-2.5">
              <button
                type="button"
                disabled={disabled}
                onClick={() => onChange({ file_id: f.id })}
                className={cn(
                  "flex min-w-0 flex-1 items-center gap-2 text-left text-sm",
                  source.file_id === f.id ? "font-semibold text-primary" : "hover:underline",
                )}
              >
                <span className="truncate">{f.filename}</span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {f.words.toLocaleString()} words
                </span>
              </button>
              <button
                type="button"
                className="text-xs text-muted-foreground hover:text-destructive"
                onClick={() => void removeFile(f.id)}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}

      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
