import { apiBaseUrl } from "@/lib/config";

export default function HomePage() {
  return (
    <main>
      <h1>Pulse</h1>
      <a href={`${apiBaseUrl()}/health`}>API health</a>
    </main>
  );
}
