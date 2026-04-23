import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Garmin Markdown Export",
  description: "Export Markdown local pour activites Garmin.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}

