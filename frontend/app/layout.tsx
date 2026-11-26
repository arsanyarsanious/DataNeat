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
import "./auto-cleaning-survey.css";
import "./premium-theme.css";
import "./skeleton.css";
import { AccountAccess } from "@/components/account-access";
const manrope = localFont({
  src: "./fonts/InterVariable.woff2",
  variable: "--font-dataneat",
  weight: "100 900",
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
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `try{if(localStorage.getItem("dataneat-theme")==="light"){document.documentElement.classList.remove("dark");}else{document.documentElement.classList.add("dark");}}catch(e){}`,
          }}
        />
      </head>
      <body className={manrope.variable}><AccountAccess>{children}</AccountAccess></body>
    </html>
  );
}
