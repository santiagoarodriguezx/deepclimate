import type { Metadata } from "next";
import { Overview } from "@/components/dashboard/overview";

export const metadata: Metadata = { title: "Panorama ambiental" };

export default function HomePage() {
  return <Overview />;
}
