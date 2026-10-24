import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Research Assistant",
  description: "Agentic research assistant over the team's research notes",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
