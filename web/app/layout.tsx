import type { ReactNode } from "react";
import "./globals.css";

// the tab icon is app/icon.svg (the file convention)
export const metadata = { title: "textchef" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
