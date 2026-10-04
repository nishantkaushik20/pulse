import { ClerkProvider } from "@clerk/nextjs";
import type { ReactNode } from "react";

import { ClerkReady } from "@/components/auth/ClerkReady";
import { clerkPublishableKey } from "@/lib/clerk";

import "./globals.css";

export const metadata = {
  title: "Pulse",
  description: "Pulse business operations",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  const publishableKey = clerkPublishableKey();
  return (
    <html lang="en">
      <body>
        {publishableKey ? (
          <ClerkProvider
            publishableKey={publishableKey}
            signInUrl="/sign-in"
            signUpUrl="/sign-up"
          >
            <ClerkReady ready>{children}</ClerkReady>
          </ClerkProvider>
        ) : (
          <ClerkReady ready={false}>{children}</ClerkReady>
        )}
      </body>
    </html>
  );
}
