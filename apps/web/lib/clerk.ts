/** Publishable key only. The secret stays on the server and is not read here. */

export function clerkPublishableKey(): string | null {
  const value = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY?.trim();
  return value ? value : null;
}
