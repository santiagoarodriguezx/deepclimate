import type { ReactNode } from "react";

export function PageHeading({ eyebrow, title, description, action }: {
  eyebrow: string; title: string; description: string; action?: ReactNode;
}) {
  return <div className="mb-7 flex flex-col justify-between gap-4 sm:mb-8 sm:flex-row sm:items-end">
    <div><p className="eyebrow">{eyebrow}</p><h2 className="mt-2 text-[26px] font-medium tracking-[-.045em] sm:text-[32px]">{title}</h2><p className="mt-2 max-w-2xl text-[13px] leading-6 text-[var(--muted)]">{description}</p></div>
    {action}
  </div>;
}
