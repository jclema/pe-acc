// Known fixture hosts identify synthetic evidence, not a published source record.
const demoHosts = ["example.gob.pe", "example.com", "example.org", "example.net"];

function parseSourceUrl(value: unknown): URL | null {
  if (typeof value !== "string" || !value.trim()) return null;
  const candidate = value.trim();
  if (/\s/.test(candidate) || /[\u0000-\u001f]/.test(candidate)) return null;
  try {
    const url = new URL(candidate);
    return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password ? url : null;
  } catch {
    return null;
  }
}

export function isDemoSourceUrl(value: unknown): boolean {
  const host = parseSourceUrl(value)?.hostname.replace(/\.$/, "");
  return !!host && demoHosts.some((demo) => host === demo || host.endsWith(`.${demo}`));
}

export function safeSourceUrl(value: unknown): string | null {
  const url = parseSourceUrl(value);
  return url && !isDemoSourceUrl(value) ? url.href : null;
}
