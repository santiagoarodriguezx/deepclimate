"use client";

import { Activity, CircleCheck, CircleX, Cpu, ShieldAlert } from "lucide-react";
import { useJevDecisions, useSources } from "@/lib/hooks/use-siata";
import { formatDate } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { PageHeading } from "@/components/dashboard/page-heading";

export function OperationsCenter() {
  const decisionsQuery = useJevDecisions();
  const sourcesQuery = useSources();
  if (decisionsQuery.isLoading || sourcesQuery.isLoading) return <LoadingState />;
  const error = decisionsQuery.error ?? sourcesQuery.error;
  if (error || !decisionsQuery.data || !sourcesQuery.data) return <ErrorState message={error?.message ?? "No se pudo consultar la observabilidad."} retry={() => { void decisionsQuery.refetch(); void sourcesQuery.refetch(); }} />;
  const { external_provider: externalProvider, decisions } = decisionsQuery.data;
  const scheduledSources = sourcesQuery.data.sources.filter((source) => ["siata", "open_meteo", "nasa_power", "ideam_radar"].includes(source.id));
  const allowed = decisions.filter((decision) => decision.allowed).length;

  return <div className="space-y-5">
    <PageHeading eyebrow="CONTROL OPERATIVO · JEV" title="Decisiones con evidencia." description="Jev aplica políticas tipadas al pipeline. Cada decisión queda registrada junto a la evidencia que la justificó." />

    <section className="grid gap-3 sm:grid-cols-3" aria-label="Estado operativo">
      <Stat label="Motor de decisiones" value="Jev determinista" detail={decisionsQuery.data.engine} icon={Cpu} />
      <Stat label="Decisiones recientes" value={String(decisions.length)} detail={`${allowed} permitieron la acción`} icon={Activity} />
      <Stat label="Conector Typesafe" value="No configurado" detail="Fallback seguro activo; no se simula el servicio" icon={ShieldAlert} />
    </section>

    <Card>
      <CardHeader><div><p className="eyebrow">TRABAJOS AUTOMÁTICOS</p><h2 className="mt-1.5 text-base font-medium">Fuentes independientes</h2></div><Badge><span className="size-1.5 rounded-full bg-[var(--fg)]" />Backend</Badge></CardHeader>
      <CardContent className="grid gap-2 pt-4 sm:grid-cols-2 xl:grid-cols-4">
        {scheduledSources.map((source) => <div key={source.id} className="rounded-xl border border-[var(--line)] p-3.5">
          <div className="flex items-center justify-between gap-2"><p className="text-xs font-medium">{source.name.split(" · ")[0]}</p><Badge>{labelStatus(source.status)}</Badge></div>
          <p className="mt-2 text-[10px] leading-4 text-[var(--muted)]">{source.update_frequency}</p>
          <p className="mt-1 text-[10px] text-[var(--muted)]">{source.last_run ? `Última ejecución ${formatDate(source.last_run.finished_at)}` : "Aún no hay una ejecución registrada"}</p>
          {source.last_run?.error_message && <p className="mt-2 line-clamp-2 text-[10px] text-[var(--muted)]">{source.last_run.error_message}</p>}
        </div>)}
      </CardContent>
    </Card>

    <Card>
      <CardHeader><div><p className="eyebrow">AUDITORÍA DE POLÍTICAS</p><h2 className="mt-1.5 text-base font-medium">Registro de decisiones</h2></div><Badge>{decisions.length} recientes</Badge></CardHeader>
      <CardContent className="pt-4">
        {!decisions.length ? <div className="py-6 text-center text-xs text-[var(--muted)]">Aún no se han guardado decisiones. El scheduler las registrará al evaluar fuentes o modelos.</div> : <div className="divide-y divide-[var(--line)]">
          {decisions.map((decision) => <article key={decision.id} className="grid gap-2 py-4 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:items-start">
            <div className="flex items-center gap-2">{decision.allowed ? <CircleCheck className="size-4" /> : <CircleX className="size-4 text-[var(--muted)]" />}<span className="text-[10px] uppercase tracking-wider text-[var(--muted)]">{decision.action.replaceAll("_", " ")}</span></div>
            <div><p className="text-xs font-medium">{decision.subject}</p><p className="mt-1 text-[11px] leading-5 text-[var(--muted)]">{decision.reason}</p>
              {Object.keys(decision.metadata).length > 0 && <dl className="mt-2 flex flex-wrap gap-1.5">{Object.entries(decision.metadata).map(([key, value]) => <div key={key} className="rounded-md border border-[var(--line)] px-2 py-1 text-[9px] text-[var(--muted)]"><dt className="inline">{key.replaceAll("_", " ")}: </dt><dd className="inline font-mono">{formatEvidence(value)}</dd></div>)}</dl>}
            </div>
            <time className="text-[10px] text-[var(--muted)] sm:text-right">{formatDate(decision.created_at)}</time>
          </article>)}
        </div>}
      </CardContent>
    </Card>

    <p className="rounded-xl border border-[var(--line)] bg-[var(--surface)] px-4 py-3 text-[11px] leading-5 text-[var(--muted)]"><ShieldAlert className="mr-2 inline size-3.5 align-[-2px]" />{externalProvider.reason} Se requiere el contrato oficial de integración Typesafe antes de habilitar llamadas externas. El fallback no puede ejecutar operaciones arbitrarias; la promoción de modelos sigue validaciones deterministas.</p>
  </div>;
}

function Stat({ label, value, detail, icon: Icon }: { label: string; value: string; detail: string; icon: typeof Cpu }) {
  return <Card><CardContent className="flex justify-between gap-3 py-4"><div><p className="text-xs text-[var(--muted)]">{label}</p><p className="mt-2 text-lg font-medium">{value}</p><p className="mt-1 text-[10px] text-[var(--muted)]">{detail}</p></div><Icon className="mt-1 size-4 text-[var(--muted)]" /></CardContent></Card>;
}

function labelStatus(status: string) {
  if (["success", "available"].includes(status)) return "Operativa";
  if (["partial", "empty"].includes(status)) return status === "empty" ? "Sin novedades" : "Parcial";
  if (status === "error") return "Error";
  return "En espera";
}

function formatEvidence(value: unknown) {
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3);
  if (typeof value === "boolean") return value ? "sí" : "no";
  return String(value ?? "—");
}
