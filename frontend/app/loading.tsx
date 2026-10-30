import { Skeleton } from "@/components/ui/states";

export default function Loading() {
  return <main className="mx-auto max-w-6xl space-y-6 px-6 py-10"><Skeleton className="h-8 w-56" /><Skeleton className="h-28 w-full" /><div className="grid gap-4 md:grid-cols-2"><Skeleton className="h-64" /><Skeleton className="h-64" /></div></main>;
}
