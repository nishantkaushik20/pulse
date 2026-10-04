import type { AttentionItem } from "@/lib/attention";

import { AttentionEmptyState } from "./AttentionEmptyState";
import { AttentionList } from "./AttentionList";
import { AttentionSummary } from "./AttentionSummary";

export type AttentionViewState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; items: AttentionItem[]; notice: string | null };

type AttentionViewProps = {
  state: AttentionViewState;
  now: Date;
  onResolve: (id: string) => void;
  onRetry: () => void;
};

export function AttentionView({ state, now, onResolve, onRetry }: AttentionViewProps) {
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
        <AttentionEmptyState />
      </main>
    );
  }
  return (
    <main className="inbox">
      <AttentionSummary count={state.items.length} />
      {state.notice ? <p role="alert">{state.notice}</p> : null}
      <AttentionList items={state.items} now={now} onResolve={onResolve} />
    </main>
  );
}
