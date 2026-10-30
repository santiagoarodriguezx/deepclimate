"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { MapPin, Search, SlidersHorizontal } from "lucide-react";
import { useLatest, useStations } from "@/lib/hooks/use-siata";
import { formatDate, formatValue, isRecent } from "@/lib/utils";
import { VARIABLES, variableMeta } from "@/lib/types";
import type { Station } from "@/lib/types";
import { PageHeading } from "@/components/dashboard/page-heading";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { MapLoader } from "@/components/stations/map-loader";

const EMPTY_STATIONS: Station[] = [];

export function StationExplorer() {
  const [search, setSearch] = useState("");
  const [type, setType] = useState("all");
  const [municipality, setMunicipality] = useState("all");
  const [variable, setVariable] = useState("PM25");
  const stationsQuery = useStations();
  const readingsQuery = useLatest(variable);
  const allStations = stationsQuery.data ?? EMPTY_STATIONS;
  const readings = readingsQuery.data ?? [];
  const municipalities = useMemo(() => [...new Set(allStations.map((station) => station.municipality).filter(Boolean))].sort(), [allStations]);
  const stations = useMemo(() => allStations.filter((station) => {
    const matchesSearch = `${station.name} ${station.code ?? ""} ${station.municipality ?? ""}`.toLocaleLowerCase("es-CO").includes(search.toLocaleLowerCase("es-CO"));
    return matchesSearch && (type === "all" || station.station_type === type) && (municipality === "all" || station.municipality === municipality);
  }), [allStations, search, type, municipality]);
  const readingByStation = new Map(readings.map((reading) => [reading.station_id, reading]));
  const problem = stationsQuery.error ?? readingsQuery.error;

  return <>
    <PageHeading eyebrow="INVENTARIO OFICIAL" title="Estaciones SIATA" description="Busca estaciones, consulta su ubicación y distingue las mediciones recientes del histórico disponible." action={<Badge>{allStations.length} en inventario</Badge>} />
    <Card className="mb-4"><CardContent className="grid gap-3 py-4 md:grid-cols-[minmax(220px,1fr)_190px_190px_190px]">
      <label className="relative"><span className="sr-only">Buscar estación, código o municipio</span><Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[var(--muted)]" /><Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar estación, código o municipio" className="pl-9" /></label>
      <label className="flex items-center gap-2"><span className="sr-only">Red</span><SlidersHorizontal className="size-3.5 text-[var(--muted)]" /><Select className="w-full" value={type} onChange={(e) => setType(e.target.value)}><option value="all">Todas las redes</option><option value="air_quality">Calidad del aire</option><option value="meteorology">Meteorología</option><option value="pluviometric">Pluviómetros</option><option value="stream_level">Nivel de cauce</option></Select></label>
      <label><span className="sr-only">Municipio</span><Select className="w-full" value={municipality} onChange={(e) => setMunicipality(e.target.value)}><option value="all">Todos los municipios</option>{municipalities.map((name) => <option key={name} value={name!}>{name}</option>)}</Select></label>
      <label><span className="sr-only">Variable</span><Select className="w-full" value={variable} onChange={(e) => setVariable(e.target.value)}>{VARIABLES.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</Select></label>
    </CardContent></Card>

    {problem && <div className="mb-4"><ErrorState message={problem.message} retry={() => { void stationsQuery.refetch(); void readingsQuery.refetch(); }} /></div>}
    <Card className="overflow-hidden">
      {stationsQuery.isLoading ? <LoadingState /> : stations.length ? <div className="overflow-x-auto"><table className="data-table min-w-[760px]"><thead><tr><th>Estación</th><th>Municipio</th><th>Red</th><th>Estado</th><th>Última observación · {variableMeta(variable).label}</th><th></th></tr></thead><tbody>{stations.map((station) => {
        const reading = readingByStation.get(station.id);
        const recent = reading && isRecent(reading.observed_at) && !["unvalidated_unit", "retrieval_timestamp"].includes(reading.quality_status);
        return <tr key={station.id}>
          <td><Link href={`/stations/${encodeURIComponent(station.id)}`} className="font-medium hover:underline">{station.name}</Link><span className="mt-1 block font-mono text-[10px] text-[var(--muted)]">{station.code ?? station.id}</span></td>
          <td>{station.municipality ?? "—"}</td>
          <td><Badge>{stationType(station.station_type)}</Badge></td>
          <td><span className="inline-flex items-center gap-2 text-[11px]"><span className={`size-1.5 rounded-full ${recent ? "bg-[var(--fg)]" : "border border-[var(--muted)]"}`} />{recent ? "Reciente" : reading ? "Antigua" : "Sin lectura"}</span></td>
          <td>{reading ? <><span className="font-mono text-xs">{formatValue(reading.value)} {reading.unit}</span><span className="mt-1 block text-[10px] text-[var(--muted)]">{formatDate(reading.observed_at)}{reading.quality_status !== "good" ? ` · ${qualityLabel(reading.quality_status)}` : ""}</span></> : <span className="text-[11px] text-[var(--muted)]">Sin medición disponible</span>}</td>
          <td><Link aria-label={`Abrir ${station.name}`} className="text-xs text-[var(--muted)] hover:text-[var(--fg)]" href={`/stations/${encodeURIComponent(station.id)}`}>Abrir →</Link></td>
        </tr>;
      })}</tbody></table></div> : <EmptyState title="No encontramos estaciones" detail="Prueba otro código, municipio o filtro de red." />}
    </Card>
    <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(300px,.8fr)]">
      <Card><div className="px-5 pt-5 sm:px-6"><p className="eyebrow">REFERENCIA GEOGRÁFICA</p><h3 className="mt-1.5 text-base font-medium">Ubicaciones publicadas</h3></div><CardContent className="pt-4"><MapLoader stations={stations} readings={readings} variable={variable} /></CardContent></Card>
      <Card><div className="px-5 pt-5 sm:px-6"><p className="eyebrow">COBERTURA DEL FILTRO</p><h3 className="mt-1.5 text-base font-medium">Qué muestran estos datos</h3></div><CardContent className="space-y-4 pt-4 text-xs leading-5 text-[var(--muted)]">
        <div className="flex gap-3"><MapPin className="mt-0.5 size-4 shrink-0" /><p>El mapa solo usa coordenadas publicadas por el inventario o la capa oficial; estaciones sin ubicación válida se mantienen en la tabla.</p></div>
        <div className="flex gap-3"><span className="mt-1 size-3 shrink-0 rounded-full bg-[var(--fg)]" /><p>“Reciente” significa una observación válida de las últimas tres horas. “Antigua” sigue disponible para consulta, pero no se presenta como lectura actual.</p></div>
        <div className="flex gap-3"><span className="mt-1 size-3 shrink-0 rounded-full border border-[var(--muted)]" /><p>Cuando el feed no incluye la hora de observación o la unidad no se ha verificado, la plataforma conserva la calidad de procedencia y lo indica.</p></div>
        <p className="border-t border-[var(--line)] pt-3">{stations.length} de {allStations.length} estaciones coinciden con los filtros actuales.</p>
      </CardContent></Card>
    </div>
  </>;
}

function stationType(value: string) {
  return ({ air_quality: "Aire", meteorology: "Meteorología", pluviometric: "Pluviómetro", stream_level: "Nivel" } as Record<string, string>)[value] ?? value;
}
function qualityLabel(value: string) {
  return ({ retrieval_timestamp: "hora de captura", unvalidated_unit: "unidad sin validar", extreme_value: "valor extremo" } as Record<string, string>)[value] ?? value;
}
