// src/app/chat/page.tsx — RAG chatbot (AI-locator) page.
// Exports: ChatPage

import { ChatClient } from "@/components/chat-client";
import { Nav } from "@/components/nav";

export default function ChatPage() {
  return (
    <main className="flex min-h-screen flex-col">
      <Nav />
      <section className="mx-auto w-full max-w-5xl flex-1 px-6 py-12">
        <h1 className="text-3xl font-semibold tracking-tight">Chatbot</h1>
        <p className="mt-2 mb-8 text-muted-foreground">
          Ask your document where the most AI content is detected and what to change.
        </p>
        <ChatClient />
      </section>
    </main>
  );
}
