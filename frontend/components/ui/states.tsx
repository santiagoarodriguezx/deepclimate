import { AlertCircle, Database, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

export function LoadingState({ label = "Cargando datos del SIATA" }: { label?: string }) {
  return <div className="flex min-h-36 items-center justify-center gap-3 text-sm text-[var(--muted)]" role="status"><LoaderCircle className="size-4 animate-spin" />{label}</div>;
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="flex min-h-36 flex-col items-center justify-center gap-3 px-5 text-center" role="alert"><AlertCircle className="size-5 text-[var(--muted)]" /><p className="max-w-md text-sm text-[var(--muted)]">{message}</p>{retry && <Button variant="outline" size="sm" onClick={retry}>Volver a intentar</Button>}</div>;
}

export function EmptyState({ title, detail }: { title: string; detail?: string }) {
  return <div className="flex min-h-36 flex-col items-center justify-center gap-2 px-5 text-center"><Database className="size-5 text-[var(--muted)]" /><p className="text-sm font-medium">{title}</p>{detail && <p className="max-w-md text-xs leading-5 text-[var(--muted)]">{detail}</p>}</div>;
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-[var(--skeleton)] ${className}`} aria-hidden="true" />;
}
