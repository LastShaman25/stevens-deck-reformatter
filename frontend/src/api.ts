import type { AiFlag, BenchmarkResult, Quality, Revision, ReviseResponse, SessionInfo } from "./types";

const BASE = "/api";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function createSession(file: File): Promise<SessionInfo> {
  const fd = new FormData();
  fd.append("file", file);
  return json<SessionInfo>(await fetch(`${BASE}/sessions`, { method: "POST", body: fd }));
}

export async function getSession(id: string): Promise<SessionInfo> {
  return json<SessionInfo>(await fetch(`${BASE}/sessions/${id}`));
}

export function previewUrl(id: string, index: number, variant: "before" | "after", bust = 0): string {
  return `${BASE}/sessions/${id}/slides/${index}/preview?variant=${variant}&v=${bust}`;
}

export async function revise(
  id: string,
  index: number,
  rev: Revision
): Promise<ReviseResponse> {
  return json(
    await fetch(`${BASE}/sessions/${id}/slides/${index}/revise`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(rev),
    })
  );
}

export async function aiCheck(
  id: string,
  index: number,
  enabled = true
): Promise<{ ok: boolean; enabled: boolean; flags: AiFlag[] }> {
  return json(
    await fetch(`${BASE}/sessions/${id}/slides/${index}/ai-check`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    })
  );
}

export async function generate(id: string): Promise<{ ok: boolean; quality: Quality; built_slides: number }> {
  return json(await fetch(`${BASE}/sessions/${id}/generate`, { method: "POST" }));
}

export async function sendToBenchmark(
  id: string,
  enabled = true,
  note = ""
): Promise<BenchmarkResult> {
  return json(
    await fetch(`${BASE}/sessions/${id}/benchmark`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled, note }),
    })
  );
}

export function downloadUrl(id: string): string {
  return `${BASE}/sessions/${id}/download`;
}

export async function purge(id: string): Promise<void> {
  await fetch(`${BASE}/sessions/${id}`, { method: "DELETE" });
}
