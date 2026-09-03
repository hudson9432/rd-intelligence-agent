import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "R&D Intelligence Agent",
  description: "Turn research evidence into R&D decisions and executable PoC plans.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
