import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = { title: "Jev · Asistente ambiental" };

export default function AssistantPage() {
  redirect("/");
}
