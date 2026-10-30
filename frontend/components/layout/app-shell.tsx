"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Command, Moon, Sun } from "lucide-react";
import { useEffect } from "react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  useEffect(() => {
    const stored = localStorage.getItem("deepclimate-theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = stored === "dark" || (!stored && prefersDark) ? "dark" : "light";
  }, []);

  function toggleTheme() {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("deepclimate-theme", next);
  }

  const title = pathname.startsWith("/stations/") ? "Detalle de estación" : "Panorama ambiental";

  return <div className="min-h-screen bg-[var(--canvas)] text-[var(--fg)]">
    <aside className="sidebar fixed inset-y-0 left-0 z-40 hidden w-[248px] flex-col border-r border-white/10 bg-[#101010] px-4 py-5 text-white lg:flex">
      <Link href="/" className="flex items-center gap-3 px-2" aria-label="DeepClimate, panorama">
        <span className="grid size-9 place-items-center rounded-full border border-white/75 text-[19px] font-light">D</span>
        <span className="text-[12px] font-semibold tracking-[.2em]">DEEPCLIMATE<span className="block pt-0.5 text-[8px] font-medium tracking-[.24em] text-white/50">METEOROLOGICAL INTELLIGENCE</span></span>
        <Command className="ml-auto size-4 text-white/30" />
      </Link>
      <div className="mt-12 px-3 text-[10px] font-medium uppercase tracking-[.19em] text-white/35">Vista central</div>
      <nav className="mt-3 grid gap-1" aria-label="Navegación principal">
        <Link href="/" aria-current="page" className="nav-link nav-link-active"><Activity className="size-4" strokeWidth={1.8} />Panorama</Link>
      </nav>
      <div className="mt-auto rounded-xl border border-white/10 bg-white/[.04] p-3">
        <div className="flex items-center gap-2 text-xs"><span className="size-1.5 rounded-full bg-white" />Pipeline backend</div>
        <div className="mt-1.5 pl-3.5 text-[10px] leading-4 text-white/45">La ingesta y los workers continúan sin el navegador abierto.</div>
      </div>
    </aside>

    <div className="lg:pl-[248px]">
      <header className="sticky top-0 z-30 border-b border-[var(--line)] bg-[var(--canvas)]/90 backdrop-blur-xl">
        <div className="mx-auto flex h-[68px] max-w-[1600px] items-center justify-between gap-4 px-4 sm:px-7 xl:px-10">
          <div className="flex min-w-0 items-center gap-3">
            <Link href="/" className="grid size-8 shrink-0 place-items-center rounded-full border border-[var(--line)] text-sm font-light lg:hidden" aria-label="DeepClimate">D</Link>
            <div className="hidden items-center gap-2 text-xs text-[var(--muted)] sm:flex"><span className="size-1.5 rounded-full bg-[var(--fg)]" /> Valle de Aburrá <span className="text-[var(--line-strong)]">/</span></div>
            <h1 className="truncate text-sm font-medium sm:text-[15px]">{title}</h1>
          </div>
          <Button variant="ghost" size="icon" aria-label="Cambiar tema claro u oscuro" onClick={toggleTheme}><Sun className="theme-light-icon" /><Moon className="theme-dark-icon" /></Button>
        </div>
      </header>
      <main id="main-content" className="mx-auto max-w-[1600px] px-4 pb-14 pt-7 sm:px-7 sm:pt-9 xl:px-10">{children}</main>
      <footer className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-2 px-4 pb-7 text-[10px] text-[var(--muted)] sm:px-7 xl:px-10"><span>DeepClimate · SIATA · IDEAM · NASA</span><span>Fuentes con escala y procedencia explícitas</span></footer>
    </div>
  </div>;
}
