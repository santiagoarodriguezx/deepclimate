import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = { title: "Laboratorio ML" };

export default function ModelsPage() {
  redirect("/");
}
