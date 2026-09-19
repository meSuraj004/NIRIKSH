import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NIRIKSH — Legal Metrology Compliance",
  description:
    "AI-assisted packaged commodity compliance inspections under Legal Metrology (Packaged Commodities) Rules, 2011.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
