export function AttentionSummary({ count, lines = [] }: { count: number; lines?: string[] }) {
  const label = count === 1 ? "1 open item" : `${count} open items`;
  return (
    <header>
      <h1>What needs your attention?</h1>
      <p>Here&apos;s what matters today.</p>
      {lines.length > 0 ? (
        <ol>
          {lines.map((line, index) => (
            <li key={`${index}-${line}`}>{line}</li>
          ))}
        </ol>
      ) : null}
      <p>Every new inbox message appears here until Pulse learns which ones matter.</p>
      <p>{label}</p>
    </header>
  );
}
