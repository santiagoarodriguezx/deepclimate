import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = { title: "Explorador satelital" };

export default function SatellitePage() {
  redirect("/");
}
