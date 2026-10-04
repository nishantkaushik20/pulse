type AttentionSummaryProps = {
  count: number;
};

export function AttentionSummary({ count }: AttentionSummaryProps) {
  const label = count === 1 ? "1 open item" : `${count} open items`;
  return (
    <header>
      <h1>What needs your attention?</h1>
      <p>Every new inbox message appears here until Pulse learns which ones matter.</p>
      <p>{label}</p>
    </header>
  );
}
