import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Finsight | Earnings intelligence",
  description:
    "Evidence-backed earnings metrics and quarterly change analysis.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
