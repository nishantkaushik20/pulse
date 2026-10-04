type AttentionSummaryProps = {
  count: number;
};

export function AttentionSummary({ count }: AttentionSummaryProps) {
  const label = count === 1 ? "1 open item" : `${count} open items`;
  return (
    <header>
      <h1>What needs your attention?</h1>
      <p>{label}</p>
    </header>
  );
}
