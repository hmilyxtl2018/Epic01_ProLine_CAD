import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";
import { Providers } from "./providers";
import { RoleSwitcher } from "@/components/RoleSwitcher";

export const metadata: Metadata = {
  title: "ProLine CAD Dashboard",
  description: "T2 W2 — ParseAgent run dashboard",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen text-zinc-900 antialiased">
        <Providers>
          <header className="border-b bg-white">
            <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
              <Link href="/sites" className="font-semibold tracking-tight">
                ProLine CAD
              </Link>
              <nav className="flex items-center gap-6 text-sm">
                <Link href="/sites" className="hover:underline">
                  Sites
                </Link>
                <Link href="/runs" className="hover:underline">
                  Runs
                </Link>
                <Link href="/quarantine" className="hover:underline">
                  Quarantine
                </Link>
                <RoleSwitcher />
              </nav>
            </div>
          </header>
          <main>{children}</main>
        </Providers>
      </body>
    </html>
  );
}
