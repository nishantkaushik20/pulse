"use client";

import { createContext, useContext, type ReactNode } from "react";

const ClerkReadyContext = createContext(false);

export function ClerkReady({ ready, children }: { ready: boolean; children: ReactNode }) {
  return <ClerkReadyContext.Provider value={ready}>{children}</ClerkReadyContext.Provider>;
}

export function useClerkReady(): boolean {
  return useContext(ClerkReadyContext);
}
