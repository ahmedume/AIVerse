// src/app/checker/page.tsx — AI + plagiarism checker page.
// Exports: CheckerPage

import { CheckerClient } from "@/components/checker-client";
import { Nav } from "@/components/nav";

export default function CheckerPage() {
  return (
    <main className="flex min-h-screen flex-col">
      <Nav />
      <section className="mx-auto w-full max-w-5xl flex-1 px-6 py-12">
        <h1 className="text-3xl font-semibold tracking-tight">Checker</h1>
        <p className="mt-2 mb-8 text-muted-foreground">
          AI detection per paragraph, plus a best-effort web plagiarism scan.
        </p>
        <CheckerClient />
      </section>
    </main>
  );
}
