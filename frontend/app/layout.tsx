import type { Metadata, Viewport } from "next";
import { Providers } from "@/components/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "SIATA Intelligence", template: "%s · SIATA Intelligence" },
  description: "Inteligencia ambiental, monitoreo de estaciones y análisis de datos SIATA para el Valle de Aburrá.",
  applicationName: "SIATA Intelligence",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#101010" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="es" suppressHydrationWarning><body><Providers>{children}</Providers></body></html>;
}
