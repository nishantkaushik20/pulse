import type { FormEvent, ReactNode } from "react";

import type { Mailbox, TenantRole } from "@/lib/setup";

type SetupPanelProps = {
  mode: "tenant" | "mailbox";
  role?: TenantRole;
  mailbox?: Mailbox | null;
  notice: string | null;
  pending: boolean;
  onCreateTenant: (name: string) => void;
  onConnect: () => void;
};

export function SetupPanel({
  mode,
  role,
  mailbox,
  notice,
  pending,
  onCreateTenant,
  onConnect,
}: SetupPanelProps) {
  return (
    <main className="inbox">
      <h1>What needs your attention?</h1>
      {notice ? <p role="status">{notice}</p> : null}
      {mode === "tenant" ? (
        <TenantForm pending={pending} onCreateTenant={onCreateTenant} />
      ) : (
        <MailboxSetup role={role ?? "MEMBER"} mailbox={mailbox ?? null} pending={pending} onConnect={onConnect} />
      )}
    </main>
  );
}

function TenantForm({
  pending,
  onCreateTenant,
}: {
  pending: boolean;
  onCreateTenant: (name: string) => void;
}) {
  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const name = String(data.get("name") ?? "");
    onCreateTenant(name);
  }

  return (
    <form onSubmit={onSubmit}>
      <p>Create your business to start seeing what needs attention.</p>
      <label>
        Business name
        <input name="name" type="text" required maxLength={200} disabled={pending} />
      </label>
      <button type="submit" disabled={pending}>
        Create business
      </button>
    </form>
  );
}

function MailboxSetup({
  role,
  mailbox,
  pending,
  onConnect,
}: {
  role: TenantRole;
  mailbox: Mailbox | null;
  pending: boolean;
  onConnect: () => void;
}) {
  return (
    <section>
      <p>Connect the Gmail inbox Pulse should watch. Pulse only reads mail. It does not send.</p>
      {mailbox ? (
        <p>
          {mailbox.externalAccountId} is {mailbox.status.toLowerCase()}.
          {mailbox.lastErrorCode ? ` Last error: ${mailbox.lastErrorCode}.` : ""}
        </p>
      ) : null}
      {role === "OWNER" ? (
        <button type="button" onClick={onConnect} disabled={pending}>
          Connect Gmail
        </button>
      ) : (
        <p>An owner needs to connect Gmail before you can sync.</p>
      )}
    </section>
  );
}

export function MailboxPanel({
  mailbox,
  role,
  pending,
  onSync,
  onDisconnect,
}: {
  mailbox: Mailbox;
  role: TenantRole;
  pending: boolean;
  onSync: () => void;
  onDisconnect: () => void;
}): ReactNode {
  return (
    <section className="mailbox">
      <p>
        {mailbox.externalAccountId} · {mailbox.status.toLowerCase()}
        {mailbox.lastSyncedAt ? ` · synced ${mailbox.lastSyncedAt}` : " · not synced yet"}
        {mailbox.lastErrorCode ? ` · ${mailbox.lastErrorCode}` : ""}
      </p>
      <button type="button" onClick={onSync} disabled={pending}>
        Sync now
      </button>
      {role === "OWNER" ? (
        <button type="button" onClick={onDisconnect} disabled={pending}>
          Disconnect
        </button>
      ) : null}
    </section>
  );
}
