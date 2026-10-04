"use client";

import { SignInButton, useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";

import { useClerkReady } from "@/components/auth/ClerkReady";
import {
  AttentionHttpError,
  loadAttention,
  resolveAttention,
  withoutItem,
} from "@/lib/attention";
import { apiBaseUrl } from "@/lib/config";

import { AttentionView, type AttentionViewState } from "./AttentionView";

export function AttentionInbox() {
  const ready = useClerkReady();
  if (!ready) {
    return (
      <AttentionView
        state={{ status: "signed-out", configured: false }}
        now={new Date()}
        onResolve={() => undefined}
        onRetry={() => undefined}
      />
    );
  }
  return <SessionInbox />;
}

function SessionInbox() {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const [remote, setRemote] = useState<AttentionViewState>({ status: "auth-loading" });
  const [now] = useState(() => new Date());
  const state = sessionView(isLoaded, isSignedIn, remote);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) {
      return;
    }
    let cancelled = false;
    void readInbox(getToken, (next) => {
      if (!cancelled) {
        setRemote(next);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [getToken, isLoaded, isSignedIn]);

  async function onRetry() {
    setRemote({ status: "loading" });
    await readInbox(getToken, setRemote);
  }

  function onResolve(id: string) {
    void (async () => {
      const token = await sessionToken(getToken);
      if (!token) {
        setRemote({ status: "signed-out", configured: true });
        return;
      }
      try {
        await resolveAttention(apiBaseUrl(), id, token);
        setRemote((current) => {
          if (current.status !== "ready") {
            return current;
          }
          return { status: "ready", items: withoutItem(current.items, id), notice: null };
        });
      } catch (error) {
        if (error instanceof AttentionHttpError && error.status === 401) {
          setRemote({ status: "signed-out", configured: true });
          return;
        }
        setRemote((current) => {
          if (current.status !== "ready") {
            return current;
          }
          return { ...current, notice: "That item could not be resolved." };
        });
      }
    })();
  }

  return (
    <AttentionView
      state={state}
      now={now}
      onResolve={onResolve}
      onRetry={() => {
        void onRetry();
      }}
      signIn={
        <SignInButton mode="redirect" fallbackRedirectUrl="/">
          <button type="button">Sign in</button>
        </SignInButton>
      }
    />
  );
}

function sessionView(
  isLoaded: boolean,
  isSignedIn: boolean | undefined,
  remote: AttentionViewState,
): AttentionViewState {
  if (!isLoaded) {
    return { status: "auth-loading" };
  }
  if (!isSignedIn) {
    return { status: "signed-out", configured: true };
  }
  if (remote.status === "auth-loading") {
    return { status: "loading" };
  }
  return remote;
}

async function readInbox(
  getToken: () => Promise<string | null>,
  setState: (state: AttentionViewState) => void,
): Promise<void> {
  const token = await sessionToken(getToken);
  if (!token) {
    setState({ status: "signed-out", configured: true });
    return;
  }
  try {
    const items = await loadAttention(apiBaseUrl(), token);
    setState({ status: "ready", items, notice: null });
  } catch (error) {
    if (error instanceof AttentionHttpError && error.status === 401) {
      setState({ status: "signed-out", configured: true });
      return;
    }
    setState({ status: "error" });
  }
}

async function sessionToken(getToken: () => Promise<string | null>): Promise<string | null> {
  try {
    return await getToken();
  } catch {
    return null;
  }
}
