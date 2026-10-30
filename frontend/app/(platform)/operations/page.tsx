import type { Metadata } from "next";
import { OperationsCenter } from "@/components/operations/operations-center";

export const metadata: Metadata = { title: "Decisiones de Jev" };

export default function OperationsPage() {
  return <OperationsCenter />;
}
