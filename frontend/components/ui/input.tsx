import type { InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn("h-10 w-full rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 text-sm text-[var(--fg)] outline-none placeholder:text-[var(--muted)] focus-visible:ring-2 focus-visible:ring-neutral-400", className)} {...props} />;
}
