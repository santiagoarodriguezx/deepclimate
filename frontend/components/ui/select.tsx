import type { SelectHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn("h-10 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 text-sm text-[var(--fg)] outline-none focus-visible:ring-2 focus-visible:ring-neutral-400", className)} {...props}>{children}</select>;
}
