import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LeadFinder AI — Discover Offline Businesses & Contact Them Instantly",
  description: "Find local businesses without websites, extract their contact details, and generate personalized outreach pitches for email, WhatsApp, social DMs, and phone calls.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
