import type { Metadata } from "next";
import { SourceCenter } from "@/components/sources/source-center";

export const metadata: Metadata = { title: "Fuentes de datos" };

export default function SourcesPage() {
  return <SourceCenter />;
}
