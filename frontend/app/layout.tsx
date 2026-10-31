import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import "./workspace-polish.css";
import "./sheet-refresh.css";
import "./interface-refresh.css";
import "./correction-refresh.css";
import "./cover-refresh.css";
import "./brand-mark.css";
import "./compact-sidebar.css";
import "./quality-tools.css";
import "./simplified-cleaning.css";
import "./dashboard-refresh.css";
import "./readability.css";
import "./sidebar-account.css";
import "./column-presentation.css";
import { AccountAccess } from "@/components/account-access";
const manrope = localFont({
  src: "./fonts/Manrope-Variable.ttf",
  variable: "--font-dataneat",
  weight: "200 800",
  display: "swap",
});
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
      <body className={manrope.variable}><AccountAccess>{children}</AccountAccess></body>
    </html>
  );
}
