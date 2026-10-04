import { groupByPriority, type AttentionItem } from "@/lib/attention";

import { AttentionCard } from "./AttentionCard";

type AttentionListProps = {
  items: AttentionItem[];
  now: Date;
  onResolve: (id: string) => void;
};

export function AttentionList({ items, now, onResolve }: AttentionListProps) {
  const groups = groupByPriority(items);
  return (
    <div>
      {groups.map((group) => (
        <section key={group.priority} aria-label={`${group.priority} priority`}>
          <h2>{group.priority}</h2>
          {group.items.map((item) => (
            <AttentionCard key={item.id} item={item} now={now} onResolve={onResolve} />
          ))}
        </section>
      ))}
    </div>
  );
}
