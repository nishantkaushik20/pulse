import { SignIn } from "@clerk/nextjs";

import { clerkPublishableKey } from "@/lib/clerk";

export default function SignInPage() {
  if (!clerkPublishableKey()) {
    return (
      <main className="inbox">
        <h1>What needs your attention?</h1>
        <p>Sign-in is not configured for this environment.</p>
      </main>
    );
  }
  return (
    <main className="inbox">
      <SignIn />
    </main>
  );
}
