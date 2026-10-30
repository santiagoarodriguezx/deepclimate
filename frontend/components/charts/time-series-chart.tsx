"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import type { EChartsOption } from "echarts";
import type { SeriesPoint } from "@/lib/types";
import { variableMeta } from "@/lib/types";
import { formatValue, parseUtcDate } from "@/lib/utils";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";

const EChart = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-[300px] animate-pulse rounded-xl bg-[var(--skeleton)]" />,
});

export function TimeSeriesChart({
  points, variable, loading, error, label,
}: {
  points?: SeriesPoint[];
  variable: string;
  loading?: boolean;
  error?: string;
  label?: string;
}) {
  const dark = useDarkTheme();
  if (loading) return <LoadingState label="Cargando serie temporal" />;
  if (error) return <ErrorState message={error} />;
  if (!points?.length) return <EmptyState title="No hay observaciones en este periodo" detail="La serie solo muestra registros almacenados con la variable y estación seleccionadas." />;

  const meta = variableMeta(variable);
  const ink = dark ? "#ededeb" : "#151515";
  const muted = dark ? "#9b9b95" : "#777772";
  const grid = dark ? "#2a2a29" : "#e9e9e6";
  const option: EChartsOption = {
    animationDuration: 300,
    grid: { left: 48, right: 20, top: 18, bottom: 35 },
    tooltip: {
      trigger: "axis",
      backgroundColor: dark ? "#171717" : "#fff",
      borderColor: dark ? "#2a2a29" : "#e7e7e3",
      textStyle: { color: ink, fontSize: 11 },
      valueFormatter: (value) => `${formatValue(Number(value), 2)} ${meta.unit}`,
    },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: points.map((point) => point.timestamp),
      axisLine: { lineStyle: { color: dark ? "#41413e" : "#cecec8" } },
      axisTick: { show: false },
      axisLabel: {
        color: muted,
        fontSize: 10,
        hideOverlap: true,
        formatter: (value: string) => {
          const date = parseUtcDate(value);
          return date ? new Intl.DateTimeFormat("es-CO", { day: "2-digit", month: "short" }).format(date) : value;
        },
      },
    },
    yAxis: {
      type: "value",
      name: meta.unit,
      nameTextStyle: { color: muted, fontSize: 10, padding: [0, 0, 4, -26] },
      axisLabel: { color: muted, fontSize: 10 },
      splitLine: { lineStyle: { color: grid } },
    },
    dataZoom: [{ type: "inside", zoomOnMouseWheel: false }, { type: "slider", height: 16, bottom: 2, borderColor: "transparent", backgroundColor: dark ? "#222" : "#f2f2f0", fillerColor: "rgba(110,110,110,.12)", handleStyle: { color: ink }, textStyle: { color: muted, fontSize: 9 } }],
    series: [{
      name: label ?? meta.label,
      type: "line",
      data: points.map((point) => point.value),
      smooth: 0.22,
      showSymbol: points.length < 36,
      symbolSize: 5,
      lineStyle: { color: ink, width: 2 },
      itemStyle: { color: ink },
      areaStyle: { color: dark ? "rgba(235,235,235,.09)" : "rgba(25,25,25,.06)" },
      emphasis: { focus: "series" },
    }],
  };

  return <div className="min-h-[290px]" role="img" aria-label={`${meta.label} ${label ? `de ${label}` : "histórica"}`}><EChart option={option} style={{ height: 310, width: "100%" }} notMerge lazyUpdate /></div>;
}

export function ForecastChart({ points, variable }: { points: Array<{ timestamp: string; prediction: number; lower: number; upper: number }>; variable: string }) {
  const dark = useDarkTheme();
  if (!points.length) return <EmptyState title="Sin pronóstico disponible" detail="Entrena el modelo con una serie horaria suficiente para generar un pronóstico." />;
  const meta = variableMeta(variable);
  const ink = dark ? "#ededeb" : "#151515";
  const muted = dark ? "#9b9b95" : "#777772";
  const grid = dark ? "#2a2a29" : "#e9e9e6";
  const option: EChartsOption = {
    animationDuration: 350,
    legend: { bottom: 0, textStyle: { color: muted, fontSize: 10 }, itemWidth: 12, itemHeight: 3 },
    grid: { left: 52, right: 20, top: 24, bottom: 48 },
    tooltip: {
      trigger: "axis",
      backgroundColor: dark ? "#171717" : "#fff",
      borderColor: dark ? "#2a2a29" : "#e7e7e3",
      textStyle: { color: ink, fontSize: 11 },
      valueFormatter: (value) => `${formatValue(Number(value), 2)} ${meta.unit}`,
    },
    xAxis: { type: "category", data: points.map((p) => p.timestamp), axisLabel: { color: muted, fontSize: 9 }, axisLine: { lineStyle: { color: dark ? "#41413e" : "#cecec8" } } },
    yAxis: { type: "value", name: meta.unit, axisLabel: { color: muted, fontSize: 10 }, splitLine: { lineStyle: { color: grid } } },
    series: [
      { name: "Predicción", type: "line", data: points.map((p) => p.prediction), smooth: 0.2, symbol: "none", lineStyle: { color: ink, width: 2.2 }, itemStyle: { color: ink } },
      { name: "Límite superior", type: "line", data: points.map((p) => p.upper), symbol: "none", lineStyle: { color: "#8a8a85", type: "dashed", width: 1 } },
      { name: "Límite inferior", type: "line", data: points.map((p) => p.lower), symbol: "none", lineStyle: { color: "#8a8a85", type: "dashed", width: 1 } },
    ],
  };
  return <div className="min-h-[300px]" role="img" aria-label={`Pronóstico de ${meta.label} con límites de incertidumbre`}><EChart option={option} style={{ height: 330, width: "100%" }} notMerge lazyUpdate /></div>;
}

export function RegionalForecastChart({ points, variable, unit }: {
  points: Array<{ timestamp: string; value: number }>;
  variable: string;
  unit: string;
}) {
  const dark = useDarkTheme();
  if (!points.length) return <EmptyState title="Pronóstico regional no disponible" detail="El conector aún no ha guardado valores para este periodo." />;
  const ink = dark ? "#ededeb" : "#151515";
  const muted = dark ? "#9b9b95" : "#777772";
  const grid = dark ? "#2a2a29" : "#e9e9e6";
  const labels = points.map((point) => parseUtcDate(point.timestamp)?.toLocaleString("es-CO", { hour: "2-digit", day: "2-digit", month: "short", timeZone: "America/Bogota" }) ?? point.timestamp);
  const option: EChartsOption = {
    animationDuration: 300,
    grid: { left: 52, right: 18, top: 24, bottom: 38 },
    tooltip: {
      trigger: "axis",
      backgroundColor: dark ? "#171717" : "#fff",
      borderColor: dark ? "#2a2a29" : "#e7e7e3",
      textStyle: { color: ink, fontSize: 11 },
      valueFormatter: (value) => `${formatValue(Number(value), 1)} ${unit}`,
    },
    xAxis: { type: "category", data: labels, boundaryGap: false, axisLabel: { color: muted, fontSize: 9, hideOverlap: true }, axisLine: { lineStyle: { color: grid } } },
    yAxis: { type: "value", min: variable === "rain_probability" ? 0 : undefined, max: variable === "rain_probability" ? 100 : undefined, name: unit, axisLabel: { color: muted, fontSize: 9 }, splitLine: { lineStyle: { color: grid } } },
    series: [{
      name: variable === "rain_probability" ? "Probabilidad de precipitación" : variable,
      type: "line",
      data: points.map((point) => point.value),
      smooth: 0.18,
      showSymbol: points.length < 24,
      symbolSize: 4,
      lineStyle: { color: ink, width: 2 },
      itemStyle: { color: ink },
      areaStyle: { color: dark ? "rgba(235,235,235,.07)" : "rgba(25,25,25,.045)" },
    }],
  };
  return <div className="min-h-[220px]" role="img" aria-label={`${variable} pronosticado por hora para la grilla regional`}><EChart option={option} style={{ height: 240, width: "100%" }} notMerge lazyUpdate /></div>;
}

function useDarkTheme() {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    const root = document.documentElement;
    const update = () => setDark(root.dataset.theme === "dark");
    update();
    const observer = new MutationObserver(update);
    observer.observe(root, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);
  return dark;
}
