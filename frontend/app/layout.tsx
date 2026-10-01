import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";

export const metadata: Metadata = {
  title: "PortfolioLab",
  description: "Portfolio analytics demo using sample data. Not investment advice.",
};

const inter = Inter({ subsets: ["latin"] });

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: `try{if(localStorage.pl_theme==="dark"||(!localStorage.pl_theme&&matchMedia("(prefers-color-scheme: dark)").matches))document.documentElement.classList.add("dark")}catch(e){}` }} /></head>
      <body className={inter.className}><AuthProvider>{children}</AuthProvider></body>
    </html>
  );
}
