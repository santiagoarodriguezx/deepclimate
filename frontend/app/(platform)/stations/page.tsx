import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = { title: "Estaciones SIATA" };

export default function StationsPage() {
  redirect("/");
}
