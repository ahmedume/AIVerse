// src/app/page.tsx — landing page presenting the three tools.
// Exports: LandingPage

import Link from "next/link";

import { Nav } from "@/components/nav";

const TOOLS = [
  {
    href: "/chat",
    name: "Chatbot",
    tag: "AI-locator",
    blurb:
      "Ask your documents. The bot finds where the most AI content is detected, what to change, and suggests how.",
  },
  {
    href: "/checker",
    name: "Checker",
    tag: "AI + plagiarism",
    blurb:
      "Paste or upload. AI detected: X% and plagiarism detected: Y% — per paragraph, with reasons and matched URLs.",
  },
  {
    href: "/remover",
    name: "Remover",
    tag: "Main tool",
    blurb:
      "Rewrite at 7 humanize levels — from maximum humanizing to corporate. Copy, or download DOCX/PDF.",
  },
];

export default function LandingPage() {
  return (
    <main className="flex min-h-screen flex-col">
      <Nav />
      <section className="mx-auto flex max-w-5xl flex-col items-center px-6 py-24 text-center">
        <p className="text-sm text-muted-foreground">
          Self-hosted · Groq API default · your files stay on your machine
        </p>
        <h1 className="mt-6 max-w-3xl text-5xl font-semibold leading-[1.05] tracking-tight md:text-7xl">
          Detect AI text.
          <br />
          Check originality.
          <br />
          Rewrite it your way.
        </h1>
        <p className="mt-8 max-w-xl text-lg text-muted-foreground">
          Where is the AI content, how much, and what to change — then humanize on a 1-7 dial and
          export as DOCX or PDF.
        </p>
        <Link
          href="/remover"
          className="mt-10 bg-foreground px-8 py-4 text-lg font-medium text-background transition-opacity hover:opacity-85"
        >
          Open the Remover
        </Link>
      </section>
      <section className="mx-auto grid w-full max-w-5xl grid-cols-1 gap-6 px-6 pb-24 md:grid-cols-3">
        {TOOLS.map((tool) => (
          <Link
            key={tool.href}
            href={tool.href}
            className="flex flex-col gap-3 rounded-xl border p-6 transition-colors hover:bg-muted"
          >
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold tracking-tight">{tool.name}</h2>
              <span className="text-xs text-muted-foreground">{tool.tag}</span>
            </div>
            <p className="text-sm leading-relaxed text-muted-foreground">{tool.blurb}</p>
          </Link>
        ))}
      </section>
      <footer className="mx-auto w-full max-w-5xl border-t px-6 py-6 text-center text-xs text-muted-foreground">
        AIverse · no cloud, no lock-in · best-effort originality checks via DuckDuckGo
      </footer>
    </main>
  );
}
