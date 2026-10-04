"use client";

import { useEffect, useState } from "react";

import { loadAttention, resolveAttention, withoutItem } from "@/lib/attention";
import { apiBaseUrl } from "@/lib/config";

import { AttentionView, type AttentionViewState } from "./AttentionView";

export function AttentionInbox() {
  const [state, setState] = useState<AttentionViewState>({ status: "loading" });
  const [now] = useState(() => new Date());

  useEffect(() => {
    let cancelled = false;
    loadAttention(apiBaseUrl())
      .then((items) => {
        if (!cancelled) {
          setState({ status: "ready", items, notice: null });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState({ status: "error" });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function onRetry() {
    setState({ status: "loading" });
    loadAttention(apiBaseUrl())
      .then((items) => setState({ status: "ready", items, notice: null }))
      .catch(() => setState({ status: "error" }));
  }

  function onResolve(id: string) {
    resolveAttention(apiBaseUrl(), id)
      .then(() => {
        setState((current) => {
          if (current.status !== "ready") {
            return current;
          }
          return { status: "ready", items: withoutItem(current.items, id), notice: null };
        });
      })
      .catch(() => {
        setState((current) => {
          if (current.status !== "ready") {
            return current;
          }
          return { ...current, notice: "That item could not be resolved." };
        });
      });
  }

  return <AttentionView state={state} now={now} onResolve={onResolve} onRetry={onRetry} />;
}
