import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Badge({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn("inline-flex items-center gap-1.5 rounded-full border border-[var(--line)] px-2.5 py-1 text-[10px] font-medium text-[var(--muted)]", className)} {...props} />;
}
