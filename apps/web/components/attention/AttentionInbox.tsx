"use client";

import { SignInButton, useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";

import { useClerkReady } from "@/components/auth/ClerkReady";
import { MailboxPanel, SetupPanel } from "@/components/setup/SetupPanel";
import {
  AttentionHttpError,
  dismissAttention,
  loadAttention,
  loadBriefing,
  resolveAttention,
  withoutItem,
} from "@/lib/attention";
import { apiBaseUrl } from "@/lib/config";
import {
  createTenant,
  disconnectMailbox,
  gmailRedirectNotice,
  loadWorkspace,
  startGmailConnect,
  syncMailbox,
  SetupHttpError,
  type Mailbox,
  type TenantRole,
  type Workspace,
} from "@/lib/setup";

import { AttentionView, type AttentionViewState } from "./AttentionView";

type SessionState =
  | { status: "auth-loading" }
  | { status: "signed-out"; configured: boolean }
  | { status: "loading" }
  | { status: "error" }
  | { status: "needs-tenant"; notice: string | null; pending: boolean }
  | {
      status: "needs-mailbox";
      role: TenantRole;
      mailbox: Mailbox | null;
      notice: string | null;
      pending: boolean;
    }
  | {
      status: "ready";
      workspace: Extract<Workspace, { kind: "ready" }>;
      attention: AttentionViewState;
      pending: boolean;
    };

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
  const [remote, setRemote] = useState<SessionState>({ status: "auth-loading" });
  const [now] = useState(() => new Date());
  const redirectNotice = gmailRedirectNotice(
    typeof window === "undefined" ? "" : window.location.search,
  );

  useEffect(() => {
    if (!isLoaded || !isSignedIn) {
      return;
    }
    let cancelled = false;
    void refresh(getToken, redirectNotice, (next) => {
      if (!cancelled) {
        setRemote(next);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [getToken, isLoaded, isSignedIn, redirectNotice]);

  if (!isLoaded) {
    return (
      <AttentionView
        state={{ status: "auth-loading" }}
        now={now}
        onResolve={() => undefined}
        onRetry={() => undefined}
      />
    );
  }
  if (!isSignedIn || remote.status === "signed-out") {
    return (
      <AttentionView
        state={{ status: "signed-out", configured: true }}
        now={now}
        onResolve={() => undefined}
        onRetry={() => undefined}
        signIn={
          <SignInButton mode="redirect" fallbackRedirectUrl="/">
            <button type="button">Sign in</button>
          </SignInButton>
        }
      />
    );
  }
  if (remote.status === "auth-loading" || remote.status === "loading") {
    return (
      <AttentionView
        state={{ status: "loading" }}
        now={now}
        onResolve={() => undefined}
        onRetry={() => undefined}
      />
    );
  }
  if (remote.status === "error") {
    return (
      <AttentionView
        state={{ status: "error" }}
        now={now}
        onResolve={() => undefined}
        onRetry={() => {
          void refresh(getToken, redirectNotice, setRemote);
        }}
      />
    );
  }
  if (remote.status === "needs-tenant") {
    return (
      <SetupPanel
        mode="tenant"
        notice={remote.notice}
        pending={remote.pending}
        onCreateTenant={(name) => {
          void runTenantCreate(getToken, name, redirectNotice, setRemote);
        }}
        onConnect={() => undefined}
      />
    );
  }
  if (remote.status === "needs-mailbox") {
    return (
      <SetupPanel
        mode="mailbox"
        role={remote.role}
        mailbox={remote.mailbox}
        notice={remote.notice}
        pending={remote.pending}
        onCreateTenant={() => undefined}
        onConnect={() => {
          void runConnect(getToken, setRemote);
        }}
      />
    );
  }

  const attention = remote.attention;
  return (
    <AttentionView
      state={attention.status === "auth-loading" ? { status: "loading" } : attention}
      now={now}
      onResolve={(id) => {
        void runResolve(getToken, id, setRemote);
      }}
      onDismiss={(id, reason) => {
        void runDismiss(getToken, id, reason, setRemote);
      }}
      onRetry={() => {
        void refresh(getToken, redirectNotice, setRemote);
      }}
      mailbox={
        <MailboxPanel
          mailbox={remote.workspace.mailbox}
          role={remote.workspace.role}
          pending={remote.pending}
          onSync={() => {
            void runSync(getToken, remote.workspace.mailbox.id, redirectNotice, setRemote);
          }}
          onDisconnect={() => {
            void runDisconnect(getToken, remote.workspace.mailbox.id, redirectNotice, setRemote);
          }}
        />
      }
    />
  );
}

async function refresh(
  getToken: () => Promise<string | null>,
  notice: string | null,
  setState: (state: SessionState) => void,
): Promise<void> {
  const token = await sessionToken(getToken);
  if (!token) {
    setState({ status: "signed-out", configured: true });
    return;
  }
  try {
    const workspace = await loadWorkspace(apiBaseUrl(), token);
    if (workspace.kind === "needs-tenant") {
      setState({ status: "needs-tenant", notice, pending: false });
      return;
    }
    if (workspace.kind === "needs-mailbox") {
      setState({
        status: "needs-mailbox",
        role: workspace.role,
        mailbox: workspace.mailbox,
        notice,
        pending: false,
      });
      return;
    }
    const items = await loadAttention(apiBaseUrl(), token);
    const briefing = await loadBriefing(apiBaseUrl(), token);
    setState({
      status: "ready",
      workspace,
      pending: false,
      attention: { status: "ready", items, briefing, notice: null },
    });
  } catch (error) {
    if (isUnauthorized(error)) {
      setState({ status: "signed-out", configured: true });
      return;
    }
    setState({ status: "error" });
  }
}

async function runTenantCreate(
  getToken: () => Promise<string | null>,
  name: string,
  notice: string | null,
  setState: (state: SessionState) => void,
): Promise<void> {
  const token = await sessionToken(getToken);
  if (!token) {
    setState({ status: "signed-out", configured: true });
    return;
  }
  setState({ status: "needs-tenant", notice, pending: true });
  try {
    await createTenant(apiBaseUrl(), token, name);
    await refresh(getToken, notice, setState);
  } catch (error) {
    if (isUnauthorized(error)) {
      setState({ status: "signed-out", configured: true });
      return;
    }
    setState({ status: "needs-tenant", notice: "That business could not be created.", pending: false });
  }
}

async function runConnect(
  getToken: () => Promise<string | null>,
  setState: (state: SessionState) => void,
): Promise<void> {
  const token = await sessionToken(getToken);
  if (!token) {
    setState({ status: "signed-out", configured: true });
    return;
  }
  try {
    const url = await startGmailConnect(apiBaseUrl(), token);
    window.location.assign(url);
  } catch (error) {
    if (isUnauthorized(error)) {
      setState({ status: "signed-out", configured: true });
      return;
    }
    setState({ status: "error" });
  }
}

async function runSync(
  getToken: () => Promise<string | null>,
  connectionId: string,
  notice: string | null,
  setState: (state: SessionState) => void,
): Promise<void> {
  const token = await sessionToken(getToken);
  if (!token) {
    setState({ status: "signed-out", configured: true });
    return;
  }
  try {
    await syncMailbox(apiBaseUrl(), token, connectionId);
    await refresh(getToken, notice, setState);
  } catch (error) {
    if (isUnauthorized(error)) {
      setState({ status: "signed-out", configured: true });
      return;
    }
    setState({ status: "error" });
  }
}

async function runDisconnect(
  getToken: () => Promise<string | null>,
  connectionId: string,
  notice: string | null,
  setState: (state: SessionState) => void,
): Promise<void> {
  const token = await sessionToken(getToken);
  if (!token) {
    setState({ status: "signed-out", configured: true });
    return;
  }
  try {
    await disconnectMailbox(apiBaseUrl(), token, connectionId);
    await refresh(getToken, notice, setState);
  } catch (error) {
    if (isUnauthorized(error)) {
      setState({ status: "signed-out", configured: true });
      return;
    }
    setState({ status: "error" });
  }
}

async function runDismiss(
  getToken: () => Promise<string | null>,
  id: string,
  reason: "not_relevant" | "done" | "waiting",
  setState: (updater: SessionState | ((current: SessionState) => SessionState)) => void,
): Promise<void> {
  const token = await sessionToken(getToken);
  if (!token) {
    setState({ status: "signed-out", configured: true });
    return;
  }
  try {
    await dismissAttention(apiBaseUrl(), id, reason, token);
    setState((current) => {
      if (current.status !== "ready" || current.attention.status !== "ready") {
        return current;
      }
      return {
        ...current,
        attention: {
          status: "ready",
          items: withoutItem(current.attention.items, id),
          briefing: withoutItem(current.attention.briefing ?? [], id),
          notice: null,
        },
      };
    });
  } catch (error) {
    if (isUnauthorized(error)) {
      setState({ status: "signed-out", configured: true });
      return;
    }
    setState((current) => {
      if (current.status !== "ready" || current.attention.status !== "ready") {
        return current;
      }
      return {
        ...current,
        attention: { ...current.attention, notice: "That item could not be dismissed." },
      };
    });
  }
}

async function runResolve(
  getToken: () => Promise<string | null>,
  id: string,
  setState: (updater: SessionState | ((current: SessionState) => SessionState)) => void,
): Promise<void> {
  const token = await sessionToken(getToken);
  if (!token) {
    setState({ status: "signed-out", configured: true });
    return;
  }
  try {
    await resolveAttention(apiBaseUrl(), id, token);
    setState((current) => {
      if (current.status !== "ready" || current.attention.status !== "ready") {
        return current;
      }
      return {
        ...current,
        attention: {
          status: "ready",
          items: withoutItem(current.attention.items, id),
          briefing: withoutItem(current.attention.briefing ?? [], id),
          notice: null,
        },
      };
    });
  } catch (error) {
    if (isUnauthorized(error)) {
      setState({ status: "signed-out", configured: true });
      return;
    }
    setState((current) => {
      if (current.status !== "ready" || current.attention.status !== "ready") {
        return current;
      }
      return {
        ...current,
        attention: { ...current.attention, notice: "That item could not be resolved." },
      };
    });
  }
}

async function sessionToken(getToken: () => Promise<string | null>): Promise<string | null> {
  try {
    return await getToken();
  } catch {
    return null;
  }
}

function isUnauthorized(error: unknown): boolean {
  return (
    (error instanceof SetupHttpError || error instanceof AttentionHttpError) && error.status === 401
  );
}
