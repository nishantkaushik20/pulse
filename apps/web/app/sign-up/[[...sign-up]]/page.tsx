import { SignUp } from "@clerk/nextjs";

import { clerkPublishableKey } from "@/lib/clerk";

export default function SignUpPage() {
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
      <SignUp />
    </main>
  );
}
