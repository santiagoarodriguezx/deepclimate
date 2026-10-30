"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Activity, Bot, ChevronDown, Cloud, Command, Database, Layers3, Menu, Moon, Radar, Satellite, Server, Sun, Waves, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { syncNow } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const navigation = [
  { href: "/", label: "Panorama", icon: Activity },
  { href: "/stations", label: "Estaciones", icon: Radar },
  { href: "/sources", label: "Fuentes de datos", icon: Database },
  { href: "/satellite", label: "Satélite e IMERG", icon: Satellite },
  { href: "/models", label: "Laboratorio ML", icon: Layers3 },
  { href: "/assistant", label: "Jev · Asistente", icon: Bot },
  { href: "/operations", label: "Jev · Decisiones", icon: Server },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const sync = useMutation({
    mutationFn: syncNow,
    onSuccess: async (result) => {
      setNotice(result.status === "success" ? "Sincronización terminada" : "Sync parcial: revisa las fuentes con error");
      await queryClient.invalidateQueries();
      window.setTimeout(() => setNotice(""), 4000);
    },
    onError: (error) => {
      setNotice(`No se pudo sincronizar: ${error.message}`);
      window.setTimeout(() => setNotice(""), 5000);
    },
  });

  useEffect(() => {
    const stored = localStorage.getItem("siata-theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const value = stored === "dark" || (!stored && prefersDark) ? "dark" : "light";
    document.documentElement.dataset.theme = value;
  }, []);

  function toggleTheme() {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("siata-theme", next);
  }

  const title = navigation.find((item) => item.href === pathname)?.label ??
    (pathname.startsWith("/stations/") ? "Detalle de estación" : "SIATA Intelligence");

  return (
    <div className="min-h-screen bg-[var(--canvas)] text-[var(--fg)]">
      <aside className="sidebar fixed inset-y-0 left-0 z-40 hidden w-[248px] flex-col border-r border-white/10 bg-[#101010] px-4 py-5 text-white lg:flex">
        <Brand />
        <div className="mt-12 px-3 text-[10px] font-medium uppercase tracking-[.19em] text-white/35">Red ambiental</div>
        <nav className="mt-3 grid gap-1" aria-label="Navegación principal">
          {navigation.map((item) => <NavItem key={item.href} {...item} active={item.href === pathname || (item.href !== "/" && pathname.startsWith(`${item.href}/`))} />)}
        </nav>
        <div className="mt-10 px-3 text-[10px] font-medium uppercase tracking-[.19em] text-white/35">Explorar</div>
        <nav className="mt-3 grid gap-1" aria-label="Vistas adicionales">
          <Link href="/stations?variable=temperature" className="nav-link"><Cloud className="size-4" /> Meteorología</Link>
          <Link href="/stations?variable=rain" className="nav-link"><Waves className="size-4" /> Precipitación</Link>
        </nav>
        <div className="mt-auto rounded-xl border border-white/10 bg-white/[.04] p-3">
          <div className="flex items-center gap-2 text-xs"><span className="size-1.5 rounded-full bg-white" /> SIATA · Valle de Aburrá</div>
          <div className="mt-1.5 pl-3.5 text-[10px] text-white/45">Observaciones oficiales</div>
        </div>
        <a className="mt-4 flex items-center gap-2 px-3 py-2 text-[11px] text-white/45 hover:text-white" href={`${process.env.NEXT_PUBLIC_BACKEND_DOCS ?? "http://127.0.0.1:8000"}/docs`} target="_blank" rel="noreferrer"><Database className="size-3.5" /> Documentación API <span className="ml-auto">↗</span></a>
      </aside>

      <div className="lg:pl-[248px]">
        <header className="sticky top-0 z-30 border-b border-[var(--line)] bg-[var(--canvas)]/90 backdrop-blur-xl">
          <div className="mx-auto flex h-[68px] max-w-[1600px] items-center justify-between gap-4 px-4 sm:px-7 xl:px-10">
            <div className="flex min-w-0 items-center gap-3">
              <Button variant="ghost" size="icon" className="lg:hidden" aria-label={mobileOpen ? "Cerrar navegación" : "Abrir navegación"} onClick={() => setMobileOpen(!mobileOpen)}>{mobileOpen ? <X /> : <Menu />}</Button>
              <div className="hidden items-center gap-2 text-xs text-[var(--muted)] sm:flex"><span className="size-1.5 rounded-full bg-[var(--fg)]" /> AMVA <span className="text-[var(--line-strong)]">/</span></div>
              <h1 className="truncate text-sm font-medium sm:text-[15px]">{title}</h1>
            </div>
            <div className="flex shrink-0 items-center gap-2 sm:gap-3">
              <Badge className="hidden sm:inline-flex"><span className="size-1.5 rounded-full bg-[var(--fg)]" /> Datos SIATA</Badge>
              <Button variant="ghost" size="icon" aria-label="Cambiar tema claro u oscuro" onClick={toggleTheme}><Sun className="theme-light-icon" /><Moon className="theme-dark-icon" /></Button>
              <Button size="sm" onClick={() => sync.mutate()} disabled={sync.isPending} className="h-9"><Database className={cn("size-3.5", sync.isPending && "animate-pulse")} /><span className="hidden sm:inline">{sync.isPending ? "Sincronizando" : "Sincronizar"}</span></Button>
            </div>
          </div>
          {mobileOpen && <nav className="grid gap-1 border-t border-[var(--line)] p-3 lg:hidden" aria-label="Navegación móvil">{navigation.map((item) => <NavItem key={item.href} {...item} active={item.href === pathname} onClick={() => setMobileOpen(false)} />)}</nav>}
          {sync.isPending && <div className="h-0.5 animate-pulse bg-neutral-800 dark:bg-neutral-200" />}
        </header>
        {notice && <div className="mx-auto max-w-[1600px] px-4 pt-3 sm:px-7 xl:px-10" role="status"><div className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-4 py-2.5 text-xs">{notice}</div></div>}
        <main id="main-content" className="mx-auto max-w-[1600px] px-4 pb-14 pt-7 sm:px-7 sm:pt-9 xl:px-10">{children}</main>
        <footer className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-2 px-4 pb-7 text-[10px] text-[var(--muted)] sm:px-7 xl:px-10"><span>SIATA Intelligence · Valle de Aburrá</span><span>La hora de captura no sustituye la hora de observación</span></footer>
      </div>
    </div>
  );
}

function Brand() {
  return <Link href="/" className="flex items-center gap-3 px-2" aria-label="SIATA Intelligence, panorama"><span className="grid size-9 place-items-center rounded-full border border-white/75 text-[19px] font-light">S</span><span className="text-[12px] font-semibold tracking-[.2em]">SIATA<span className="block pt-0.5 text-[8px] font-medium tracking-[.24em] text-white/50">INTELLIGENCE</span></span><Command className="ml-auto size-4 text-white/30" /></Link>;
}

function NavItem({ href, label, icon: Icon, active, onClick }: {
  href: string; label: string; icon: typeof Activity; active: boolean; onClick?: () => void;
}) {
  return <Link href={href} onClick={onClick} aria-current={active ? "page" : undefined} className={cn("nav-link", active && "nav-link-active")}><Icon className="size-4" strokeWidth={1.8} />{label}{active && <ChevronDown className="ml-auto size-3 -rotate-90" />}</Link>;
}
