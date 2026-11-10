import { ClerkProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import { Geist, Geist_Mono, Urbanist } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
const urbanist = Urbanist({ variable: "--font-urbanist", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Meridian Intelligence",
  description: "Privacy-first document checks for warehouse receiving.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <ClerkProvider
      appearance={{
        variables: { colorPrimary: "#c2410c", borderRadius: "0.9rem", fontFamily: "var(--font-geist-sans)" },
        elements: { card: { boxShadow: "0 1px 2px rgb(0 0 0 / 0.04)", border: "1px solid #e5e5e5" } },
      }}
    >
      <html lang="en" className={`${geistSans.variable} ${geistMono.variable} ${urbanist.variable}`}>
        <body className="antialiased">{children}</body>
      </html>
    </ClerkProvider>
  );
}
