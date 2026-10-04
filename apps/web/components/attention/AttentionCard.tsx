import { formatAge } from "@/lib/age";
import { attentionContext, type AttentionItem } from "@/lib/attention";

type AttentionCardProps = {
  item: AttentionItem;
  now: Date;
  onResolve: (id: string) => void;
  onDismiss: (id: string, reason: "not_relevant" | "done" | "waiting") => void;
};

export function AttentionCard({ item, now, onResolve, onDismiss }: AttentionCardProps) {
  const context = attentionContext(item.description);
  return (
    <article>
      <h3>{item.title}</h3>
      {context.from ? <p>{context.from}</p> : null}
      {item.customer_name ? <p>Customer: {item.customer_name}</p> : null}
      {context.subject ? <p>{context.subject}</p> : null}
      {context.text ? <p>{context.text}</p> : null}
      <p>
        <time dateTime={item.created_at}>{formatAge(item.created_at, now)}</time>
      </p>
      <button type="button" onClick={() => onResolve(item.id)}>
        Resolve
      </button>
      <button type="button" onClick={() => onDismiss(item.id, "not_relevant")}>
        Not relevant
      </button>
    </article>
  );
}
