"use client";

import Link from "next/link";
import { Activity, ArrowUpRight, Check, CircleAlert, Database, Satellite, Waves } from "lucide-react";
import { useSources } from "@/lib/hooks/use-siata";
import { formatDate } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { PageHeading } from "@/components/dashboard/page-heading";
import type { Source } from "@/lib/types";

export function SourceCenter() {
  const query = useSources();
  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) return <ErrorState message={query.error?.message ?? "No se pudo consultar el registro de fuentes."} retry={() => void query.refetch()} />;

  const sources = query.data.sources;
  const automated = sources.filter((source) => ["siata", "open_meteo", "nasa_power", "ideam_radar"].includes(source.id));
  const active = automated.filter((source) => ["success", "empty", "partial"].includes(source.status)).length;
  const failures = automated.filter((source) => source.status === "error").length;

  return <div className="space-y-5">
    <PageHeading eyebrow="OBSERVABILIDAD · PROCEDENCIA" title="Fuentes y calidad del pipeline." description="Estado consultado del registro de conectores, sus últimas ejecuciones y las limitaciones verificadas de cada producto." action={<Link href="/operations"><Button variant="secondary" size="sm"><Activity className="size-3.5" /> Ver decisiones de Jev</Button></Link>} />

    <section className="grid gap-3 sm:grid-cols-3" aria-label="Resumen de fuentes">
      <Summary label="Fuentes automatizadas" value={`${active}/${automated.length}`} detail="Con al menos una ejecución registrada" icon={Database} />
      <Summary label="Errores recientes" value={String(failures)} detail="Cada conector reintenta de forma independiente" icon={CircleAlert} />
      <Summary label="Registro consultado" value={formatDate(query.data.checked_at)} detail="Estado persistido por el backend" icon={Activity} />
    </section>

    <section className="grid gap-3 lg:grid-cols-2" aria-label="Catálogo de fuentes">
      {sources.map((source) => <SourceCard key={source.id} source={source} />)}
    </section>

    <Card className="border-dashed">
      <CardHeader><div><p className="eyebrow">LÍMITES DEL SISTEMA</p><h2 className="mt-1.5 text-base font-medium">Los productos conservan su escala y procedencia</h2></div><Satellite className="size-4 text-[var(--muted)]" /></CardHeader>
      <CardContent className="grid gap-3 pt-4 text-xs leading-5 text-[var(--muted)] sm:grid-cols-3">
        <p>NASA POWER describe el entorno regional con una grilla de decenas de kilómetros; no representa un pluviómetro ni una estación SIATA.</p>
        <p>Open-Meteo entrega valores de modelo por celda. Los pronósticos se guardan separados de las observaciones y no entrenan modelos SIATA automáticamente.</p>
        <p>GIBS e IMERG se usan como capas de visualización. No se extraen valores científicos de colores de teselas ni se interpola lluvia entre estaciones.</p>
      </CardContent>
    </Card>
  </div>;
}

function Summary({ label, value, detail, icon: Icon }: { label: string; value: string; detail: string; icon: typeof Database }) {
  return <Card><CardContent className="flex items-start justify-between gap-3 py-4"><div><p className="text-xs text-[var(--muted)]">{label}</p><p className="mt-2 text-xl font-medium tracking-tight">{value}</p><p className="mt-1 text-[10px] text-[var(--muted)]">{detail}</p></div><Icon className="mt-1 size-4 text-[var(--muted)]" /></CardContent></Card>;
}

function SourceCard({ source }: { source: Source }) {
  const run = source.last_run;
  const scan = source.availability_scan;
  const checkedSources = Array.isArray(scan?.metadata.sources)
    ? scan.metadata.sources as Array<{ id: string; status: string }>
    : [];
  const radarData = source.id === "ideam_radar" ? source.last_run?.metadata.radars : undefined;
  const radars = radarData && typeof radarData === "object" ? Object.entries(radarData as Record<string, unknown>) : [];
  const status = source.status;
  const statusLabel: Record<string, string> = {
    success: "Operativa", empty: "Sin datos nuevos", partial: "Parcial", error: "Error",
    available: "Disponible", visualization_only: "Visualización", scheduled: "Esperando primera ejecución", running: "En curso",
    not_integrated: "No integrada", metadata_only: "Solo índice", configured: "API configurada", not_configured: "Sin credencial",
  };
  const isOnline = ["success", "empty", "partial", "available", "running"].includes(status);

  return <Card className="min-w-0 transition-colors hover:border-[var(--line-strong)]">
    <CardHeader className="items-start">
      <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><p className="eyebrow">{source.category.replace(/_/g, " ")}</p><Badge><span className={`size-1.5 rounded-full ${isOnline ? "bg-[var(--fg)]" : "bg-[var(--muted)]"}`} />{statusLabel[status] ?? status}</Badge></div><h2 className="mt-2 text-[15px] font-medium tracking-tight">{source.name}</h2></div>
      <a href={source.url} target="_blank" rel="noreferrer" aria-label={`Abrir fuente ${source.name}`} className="rounded-md p-1.5 text-[var(--muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--fg)]"><ArrowUpRight className="size-4" /></a>
    </CardHeader>
    <CardContent className="pt-4">
      <div className="grid gap-3 text-xs sm:grid-cols-2">
        <Info label="Frecuencia" value={source.update_frequency} />
        <Info label="Resolución temporal" value={source.temporal_resolution} />
        <Info label="Cobertura espacial" value={source.spatial_resolution} />
        <Info label="Latencia" value={source.latency} />
      </div>
      <div className="mt-4 flex flex-wrap gap-1.5">{source.variables.map((variable) => <span key={variable} className="rounded-md border border-[var(--line)] px-2 py-1 text-[10px] text-[var(--muted)]">{variable}</span>)}</div>
      {run && <div className="mt-4 rounded-lg border border-[var(--line)] bg-[var(--canvas)] px-3 py-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2 text-[10px]"><span className="text-[var(--muted)]">{run.status === "running" ? "Ejecución en curso" : "Última ejecución"}</span><span>{formatDate(run.finished_at ?? run.started_at)} · {run.status === "running" ? "procesando" : `${run.records_count.toLocaleString("es-CO")} registros · ${run.latency_ms ?? 0} ms`}</span></div>
        {run.error_message && <p className="mt-2 text-[10px] leading-4 text-[var(--muted)]">{run.error_message}</p>}
        {radars.length > 0 && <div className="mt-3 grid grid-cols-2 gap-2">{radars.map(([name, raw]) => {
          const radar = raw as { volumes_listed?: number; latest_archive_object?: { key?: string; last_modified?: string } | null };
          return <div key={name} className="rounded-md border border-[var(--line)] px-2.5 py-2"><p className="text-[10px] font-medium">{name}</p><p className="mt-1 text-[9px] text-[var(--muted)]">{radar.volumes_listed ?? 0} volúmenes indexados</p>{radar.latest_archive_object?.last_modified && <p className="mt-1 text-[9px] text-[var(--muted)]">S3 {formatDate(radar.latest_archive_object.last_modified)}</p>}</div>;
        })}</div>}
      </div>}
      {source.id === "siata" && scan && <div className="mt-3 rounded-lg border border-[var(--line)] px-3 py-2.5">
        <div className="flex items-center justify-between gap-2 text-[10px]"><span className="text-[var(--muted)]">Escaneo de endpoints</span><span>{scan.records_count}/{checkedSources.length} disponibles · {formatDate(scan.finished_at)}</span></div>
        {scan.error_message?.trim() && <p className="mt-2 text-[10px] leading-4 text-[var(--muted)]">{scan.error_message}</p>}
      </div>}
      {source.latest_valid_time && <p className="mt-3 text-[10px] text-[var(--muted)]">Último tiempo válido: {formatDate(source.latest_valid_time)} UTC · {source.records_stored.toLocaleString("es-CO")} datos regionales almacenados</p>}
      {source.limitation && <p className="mt-3 rounded-lg border border-[var(--line)] px-3 py-2.5 text-[10px] leading-4 text-[var(--muted)]">{source.limitation}</p>}
      <p className="mt-3 flex items-start gap-1.5 text-[10px] leading-4 text-[var(--muted)]"><Check className="mt-0.5 size-3 shrink-0" />{source.license}</p>
      {source.id === "nasa_gpm" && <Link href="/satellite" className="mt-3 inline-flex items-center gap-1 text-[11px] hover:underline">Abrir IMERG en el mapa <Waves className="size-3" /></Link>}
      {source.id === "nasa_gibs" && <Link href="/satellite" className="mt-3 inline-flex items-center gap-1 text-[11px] hover:underline">Explorar imagen satelital <Satellite className="size-3" /></Link>}
      {source.id === "ideam_radar" && <a href="https://visualizador.ideam.gov.co/portal/apps/experiencebuilder/experience/?id=c874489bc74a477c82cb2622a92c4cea" target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-[11px] hover:underline">Abrir visualizador de radar IDEAM <ArrowUpRight className="size-3" /></a>}
    </CardContent>
  </Card>;
}

function Info({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0"><p className="text-[10px] text-[var(--muted)]">{label}</p><p className="mt-1 leading-4">{value}</p></div>;
}
