// src/app/chat/page.tsx — RAG chatbot (AI-locator) page.
// Exports: ChatPage

import { Nav } from "@/components/nav";

export default function ChatPage() {
  return (
    <main className="flex min-h-screen flex-col">
      <Nav />
      <section className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-6 py-12">
        <h1 className="text-3xl font-semibold tracking-tight">Chatbot</h1>
        <p className="mt-2 text-muted-foreground">
          Ask your documents where the most AI content is detected and what to change.
        </p>
        <div className="mt-8 flex flex-1 items-center justify-center rounded-xl border border-dashed p-12 text-muted-foreground">
          Coming soon — Phase 7.
        </div>
      </section>
    </main>
  );
}