import type { Metadata } from "next";
import { Big_Shoulders_Display, IBM_Plex_Mono, IBM_Plex_Sans, IBM_Plex_Sans_Arabic, Noto_Sans_KR } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const display = Big_Shoulders_Display({ subsets: ["latin"], weight: ["700", "900"], variable: "--font-display" });
const body = IBM_Plex_Sans({ subsets: ["latin", "latin-ext", "vietnamese"], weight: ["400", "500", "600"], variable: "--font-body" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono" });
const arabic = IBM_Plex_Sans_Arabic({ subsets: ["arabic"], weight: ["400", "600"], variable: "--font-arabic" });
const kr = Noto_Sans_KR({ subsets: ["latin"], weight: ["400", "600"], variable: "--font-kr", preload: false });

export const metadata: Metadata = {
  title: "STENTOR",
  description: "Every warning, in every language, verified before it is sent.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable} ${mono.variable} ${arabic.variable} ${kr.variable}`}>
      <body className="min-h-screen bg-slate-paper font-sans text-ink antialiased">
        <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:bg-white focus:px-3 focus:py-2">
          Skip to content
        </a>
        <header className="border-b-4 border-tape bg-ink text-white">
          <div className="mx-auto flex max-w-7xl items-baseline gap-6 px-4 py-3">
            <Link href="/" className="font-display text-3xl font-black uppercase tracking-wide">
              Stentor
            </Link>
            <span className="hidden text-sm text-slate-rule sm:inline">Every warning, in every language, verified before it is sent.</span>
            <nav aria-label="Main" className="ml-auto flex flex-wrap justify-end gap-x-5 gap-y-1 text-sm font-medium">
              <Link href="/" className="hover:underline">Console</Link>
              <Link href="/history" className="hover:underline">History</Link>
              <Link href="/stats" className="hover:underline">Stats</Link>
              <Link href="/lexicon" className="hover:underline">Lexicons</Link>
              <Link href="/eval" className="hover:underline">Eval</Link>
              <Link href="/how" className="hover:underline">How it works</Link>
              <Link href="/settings" className="hover:underline">Settings</Link>
            </nav>
          </div>
        </header>
        <div id="main">{children}</div>
        <footer className="mx-auto mt-10 max-w-7xl border-t border-slate-rule px-4 py-4 text-xs text-slate-mute print:hidden">
          STENTOR demo. Not certified for production alerting.{" "}
          <a className="underline" href={`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/feed.atom`}>Atom feed of alerts</a>
        </footer>
      </body>
    </html>
  );
}
