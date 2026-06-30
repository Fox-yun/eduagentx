/**
 * Mailpit API helper for Playwright E2E tests.
 *
 * Polls the Mailpit API to retrieve verification and password-reset
 * emails, extracts link tokens, and cleans up between tests.
 */

const MAILPIT_API = "http://127.0.0.1:8025/api/v1";
const POLL_INTERVAL_MS = 500;
const POLL_TIMEOUT_MS = 30_000;

interface MailpitMessageSummary {
  ID: string;
  Subject: string;
  To: Array<{ Address: string }>;
  Created: string;
}

interface MailpitMessageFull {
  ID: string;
  Subject: string;
  Text: string;
  HTML: string;
  To: Array<{ Address: string }>;
  From: { Name: string; Address: string };
  Date: string;
  Attachments: unknown[];
}

/**
 * Wait for an email to arrive in Mailpit matching the given criteria.
 * Returns the FULL message including Text and HTML body.
 * Throws if no matching email arrives within the timeout.
 */
export async function waitForEmail(
  opts: {
    subject?: string;
    recipient?: string;
  } = {},
): Promise<MailpitMessageFull> {
  const deadline = Date.now() + POLL_TIMEOUT_MS;

  while (Date.now() < deadline) {
    const res = await fetch(`${MAILPIT_API}/messages?limit=50`);
    const body = await res.json();
    const messages: MailpitMessageSummary[] = body.messages ?? [];

    for (const msg of messages) {
      if (opts.subject && !msg.Subject.includes(opts.subject)) continue;
      if (opts.recipient) {
        const addresses = msg.To.map((t) => t.Address);
        if (!addresses.includes(opts.recipient)) continue;
      }
      // Fetch full message content
      const fullRes = await fetch(`${MAILPIT_API}/message/${msg.ID}`);
      return (await fullRes.json()) as MailpitMessageFull;
    }

    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
  }

  throw new Error(
    `Mailpit: email not found within ${POLL_TIMEOUT_MS}ms` +
      (opts.subject ? ` (subject="${opts.subject}")` : "") +
      (opts.recipient ? ` (recipient="${opts.recipient}")` : ""),
  );
}

/**
 * Extract a URL matching the given path pattern from an email's text body.
 */
export function extractUrl(email: MailpitMessageFull, pathPattern: string): string {
  const text = email.Text || "";
  const html = email.HTML || "";
  const regex = new RegExp(`http[^\\s<"']+${pathPattern}[^\\s<"']*`, "i");
  const match = text.match(regex) || html.match(regex);
  if (!match) {
    throw new Error(
      `Mailpit: URL matching "${pathPattern}" not found in email. ` +
        `Text length: ${text.length}, HTML length: ${html.length}`,
    );
  }
  return match[0];
}

/**
 * Extract a token parameter value from an email's URLs.
 */
export function extractToken(email: MailpitMessageFull, pathPattern: string): string {
  const url = extractUrl(email, pathPattern);
  const tokenMatch = url.match(/[?&]token=([^&\s]+)/);
  if (!tokenMatch) {
    throw new Error(`Mailpit: token not found in URL "${url}"`);
  }
  return tokenMatch[1];
}

/**
 * Delete all messages from Mailpit (between-test cleanup).
 */
export async function deleteAllMessages(): Promise<void> {
  await fetch(`${MAILPIT_API}/messages`, { method: "DELETE" });
}
