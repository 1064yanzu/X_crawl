import type { Metadata } from "next";
import { Fraunces, Manrope, JetBrains_Mono, Noto_Sans_SC, Noto_Serif_SC } from "next/font/google";
import { AppShell } from "@/components/layout/AppShell";
import { AppProviders } from "@/components/providers/AppProviders";
import { THEME_INIT_SCRIPT } from "@/lib/theme";
import "./globals.css";

const appSerif = Fraunces({
  variable: "--font-app-serif",
  subsets: ["latin"],
  axes: ["opsz", "SOFT"],
  display: "swap",
});

const appSans = Manrope({
  variable: "--font-app-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const appCnSerif = Noto_Serif_SC({
  variable: "--font-cn-serif",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const appCnSans = Noto_Sans_SC({
  variable: "--font-cn-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const appMono = JetBrains_Mono({
  variable: "--font-app-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "X_crawl · 编辑室",
  description: "多平台采集控制台 — X / 微博 / YouTube，节奏化采集与可恢复任务流。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="zh-CN"
      className={`${appSerif.variable} ${appSans.variable} ${appCnSerif.variable} ${appCnSans.variable} ${appMono.variable} antialiased`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="min-h-screen bg-background font-sans text-foreground">
        <a href="#main-content" className="skip-link">
          跳转到主内容
        </a>
        <AppProviders>
          <AppShell>
            {children}
          </AppShell>
        </AppProviders>
      </body>
    </html>
  );
}
