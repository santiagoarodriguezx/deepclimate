import type { LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

export function MetricCard({ label, value, unit, detail, icon: Icon }: {
  label: string; value: string; unit?: string; detail: string; icon: LucideIcon;
}) {
  return <Card><CardContent className="pb-5 pt-5 sm:pt-5">
    <div className="flex items-center justify-between"><p className="eyebrow">{label}</p><Icon className="size-4 text-[var(--muted)]" strokeWidth={1.7} /></div>
    <div className="mt-5 flex items-baseline gap-2"><strong className="text-[29px] font-medium tracking-[-.055em]">{value}</strong>{unit && <span className="text-xs text-[var(--muted)]">{unit}</span>}</div>
    <p className="mt-2 truncate text-[11px] text-[var(--muted)]">{detail}</p>
  </CardContent></Card>;
}
