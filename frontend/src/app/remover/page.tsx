// src/app/remover/page.tsx — AI content remover (primary tool) page.
// Exports: RemoverPage

import { Nav } from "@/components/nav";
import { RemoverClient } from "@/components/remover-client";

export default function RemoverPage() {
  return (
    <main className="flex min-h-screen flex-col">
      <Nav />
      <section className="mx-auto w-full max-w-5xl flex-1 px-6 py-12">
        <h1 className="text-3xl font-semibold tracking-tight">Remover</h1>
        <p className="mt-2 mb-8 text-muted-foreground">
          Pick a level (1 = most human, 7 = most corporate), rewrite, then export DOCX/PDF.
        </p>
        <RemoverClient />
      </section>
    </main>
  );
}
