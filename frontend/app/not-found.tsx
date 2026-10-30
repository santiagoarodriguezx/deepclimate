import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return <main className="grid min-h-screen place-items-center p-6 text-center"><div><p className="eyebrow">404 · NO ENCONTRADO</p><h1 className="mt-3 text-3xl font-semibold">Esta vista no existe</h1><p className="my-3 text-sm text-[var(--muted)]">Regresa al panorama para explorar la red SIATA.</p><Button asChild><Link href="/">Ir al panorama</Link></Button></div></main>;
}
