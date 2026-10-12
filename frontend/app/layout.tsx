import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "DataNeat — Make room for better data",
  description:
    "Review, clean, and standardize your spreadsheets. Your data stays yours.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
