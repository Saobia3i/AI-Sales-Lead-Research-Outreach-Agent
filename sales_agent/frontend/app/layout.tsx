import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sales Lead Research Agent",
  description: "Evidence-backed company research and verified outreach drafting",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
