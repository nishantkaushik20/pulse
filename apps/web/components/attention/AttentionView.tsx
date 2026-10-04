import type { ReactNode } from "react";

import type { AttentionItem } from "@/lib/attention";

import { AttentionEmptyState } from "./AttentionEmptyState";
import { AttentionList } from "./AttentionList";
import { AttentionSummary } from "./AttentionSummary";

export type AttentionViewState =
  | { status: "auth-loading" }
  | { status: "signed-out"; configured: boolean }
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; items: AttentionItem[]; notice: string | null; briefing?: AttentionItem[] };

type AttentionViewProps = {
  state: AttentionViewState;
  now: Date;
  onResolve: (id: string) => void;
  onDismiss?: (id: string, reason: "not_relevant" | "done" | "waiting") => void;
  onRetry: () => void;
  signIn?: ReactNode;
  mailbox?: ReactNode;
};

export function AttentionView({
  state,
  now,
  onResolve,
  onDismiss = () => undefined,
  onRetry,
  signIn,
  mailbox,
}: AttentionViewProps) {
  if (state.status === "auth-loading") {
    return (
      <main className="inbox">
        <h1>What needs your attention?</h1>
        <p role="status">Checking your session.</p>
      </main>
    );
  }
  if (state.status === "signed-out") {
    return (
      <main className="inbox">
        <h1>What needs your attention?</h1>
        <p>
          {state.configured
            ? "Sign in to see what needs your attention."
            : "Sign-in is not configured for this environment."}
        </p>
        {state.configured ? signIn : null}
      </main>
    );
  }
  if (state.status === "loading") {
    return (
      <main className="inbox">
        <h1>What needs your attention?</h1>
        <p role="status">Checking what needs your attention.</p>
      </main>
    );
  }
  if (state.status === "error") {
    return (
      <main className="inbox">
        <h1>What needs your attention?</h1>
        <p role="alert">Pulse could not load what needs your attention.</p>
        <button type="button" onClick={onRetry}>
          Try again
        </button>
      </main>
    );
  }
  if (state.items.length === 0) {
    return (
      <main className="inbox">
        {mailbox}
        <AttentionEmptyState />
      </main>
    );
  }
  return (
    <main className="inbox">
      {mailbox}
      <AttentionSummary count={state.items.length} lines={(state.briefing ?? []).map((item) => item.title)} />
      {state.notice ? <p role="alert">{state.notice}</p> : null}
      <AttentionList items={state.items} now={now} onResolve={onResolve} onDismiss={onDismiss} />
    </main>
  );
}
