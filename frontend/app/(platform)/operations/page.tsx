import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = { title: "Decisiones de Jev" };

export default function OperationsPage() {
  redirect("/");
}
