export const PRIORITIES = ["HIGH", "MEDIUM", "LOW"] as const;

export type AttentionPriority = (typeof PRIORITIES)[number];

export type AttentionItem = {
  id: string;
  type: string;
  title: string;
  description: string | null;
  priority: AttentionPriority;
  status: "OPEN" | "RESOLVED";
  created_at: string;
  source: string | null;
  entity_type: string | null;
  entity_id: string | null;
};

export type AttentionContext = {
  from: string | null;
  subject: string | null;
  text: string | null;
};

export function attentionContext(description: string | null): AttentionContext {
  if (description === null || description.trim() === "") {
    return { from: null, subject: null, text: null };
  }
  let from: string | null = null;
  let subject: string | null = null;
  for (const line of description.split("\n")) {
    if (from === null && line.startsWith("From: ")) {
      from = line;
    }
    if (subject === null && line.startsWith("Subject: ")) {
      subject = line;
    }
  }
  if (from !== null || subject !== null) {
    return { from, subject, text: null };
  }
  return { from: null, subject: null, text: description };
}

export function groupByPriority(items: AttentionItem[]): Array<{
  priority: AttentionPriority;
  items: AttentionItem[];
}> {
  return PRIORITIES.map((priority) => ({
    priority,
    items: items.filter((item) => item.priority === priority),
  })).filter((group) => group.items.length > 0);
}

export function withoutItem(items: AttentionItem[], id: string): AttentionItem[] {
  return items.filter((item) => item.id !== id);
}

export async function loadAttention(
  baseUrl: string,
  fetchImpl: typeof fetch = fetch,
): Promise<AttentionItem[]> {
  const response = await fetchImpl(`${baseUrl}/attention`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error("attention request failed");
  }
  return parseInbox(await response.json());
}

export async function resolveAttention(
  baseUrl: string,
  id: string,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const response = await fetchImpl(`${baseUrl}/attention/${id}/resolve`, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error("resolve request failed");
  }
}

function parseInbox(body: unknown): AttentionItem[] {
  if (!isRecord(body) || !Array.isArray(body.items)) {
    throw new Error("attention request failed");
  }
  return body.items.map(parseItem);
}

function parseItem(value: unknown): AttentionItem {
  if (!isRecord(value)) {
    throw new Error("attention request failed");
  }
  const priority = value.priority;
  if (priority !== "HIGH" && priority !== "MEDIUM" && priority !== "LOW") {
    throw new Error("attention request failed");
  }
  const status = value.status;
  if (status !== "OPEN" && status !== "RESOLVED") {
    throw new Error("attention request failed");
  }
  return {
    id: requiredString(value.id),
    type: requiredString(value.type),
    title: requiredString(value.title),
    description: optionalString(value.description),
    priority,
    status,
    created_at: requiredString(value.created_at),
    source: optionalString(value.source),
    entity_type: optionalString(value.entity_type),
    entity_id: optionalString(value.entity_id),
  };
}

function requiredString(value: unknown): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error("attention request failed");
  }
  return value;
}

function optionalString(value: unknown): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value !== "string") {
    throw new Error("attention request failed");
  }
  return value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
