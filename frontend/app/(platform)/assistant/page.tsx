import type { Metadata } from "next";
import { AssistantPanel } from "@/components/assistant/assistant-panel";

export const metadata: Metadata = { title: "Jev · Asistente ambiental" };

export default function AssistantPage() {
  return <AssistantPanel />;
}
