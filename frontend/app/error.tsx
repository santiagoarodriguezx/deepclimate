"use client";

import { useEffect } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { console.error(error); }, [error]);
  return <main className="grid min-h-screen place-items-center bg-[var(--canvas)] p-6 text-[var(--fg)]"><div className="max-w-md text-center"><AlertTriangle className="mx-auto mb-4 size-6" /><h1 className="text-xl font-semibold">No se pudo cargar esta vista</h1><p className="my-3 text-sm text-[var(--muted)]">{error.message || "Ocurrió un error inesperado."}</p><Button onClick={reset}>Volver a intentar</Button></div></main>;
}
