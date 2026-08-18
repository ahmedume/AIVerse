// src/app/checker/page.tsx — AI + plagiarism checker page.
// Exports: CheckerPage

import { Nav } from "@/components/nav";

export default function CheckerPage() {
  return (
    <main className="flex min-h-screen flex-col">
      <Nav />
      <section className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-6 py-12">
        <h1 className="text-3xl font-semibold tracking-tight">Checker</h1>
        <p className="mt-2 text-muted-foreground">
          AI detected: X% · plagiarism detected: Y% — per paragraph, with reasons and URLs.
        </p>
        <div className="mt-8 flex flex-1 items-center justify-center rounded-xl border border-dashed p-12 text-muted-foreground">
          Coming soon — Phase 7.
        </div>
      </section>
    </main>
  );
}