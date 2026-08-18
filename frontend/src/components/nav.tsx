// src/components/nav.tsx — top navigation shared by all pages.
// Exports: Nav

import Link from "next/link";

const LINKS = [
  { href: "/chat", label: "Chatbot" },
  { href: "/checker", label: "Checker" },
  { href: "/remover", label: "Remover" },
];

export function Nav() {
  return (
    <header className="border-b bg-background/80 backdrop-blur sticky top-0 z-10">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          AIverse<span className="text-primary">.</span>
        </Link>
        <nav className="flex items-center gap-6 text-sm text-muted-foreground">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} className="transition-colors hover:text-foreground">
              {l.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}