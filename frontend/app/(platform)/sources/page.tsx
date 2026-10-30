import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = { title: "Fuentes de datos" };

export default function SourcesPage() {
  redirect("/");
}
