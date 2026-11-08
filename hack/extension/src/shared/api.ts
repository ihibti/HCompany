// Shared types + message protocol between content scripts, SW and panel.

export interface VideoMeta {
  platform: string;
  id: string;
  url: string;
  title: string;
  channel: string;
  description: string;
  hashtags: string[];
  duration?: string;
}

export interface Verdict {
  id: string;
  verdict: "on" | "off" | "unsure";
  confidence: number;
  reason: string;
}

export type Msg =
  | { kind: "fetch"; path: string; method?: string; body?: unknown }
  | { kind: "badge"; count: number }
  | { kind: "userThrow" }
  | { kind: "getState" };

export interface Counters { auto: number; manual: number; undone: number; replaced?: number }

export async function backendFetch<T>(path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  const resp = (await chrome.runtime.sendMessage({
    kind: "fetch", path, method: init?.method ?? "GET", body: init?.body,
  })) as { ok: boolean; status: number; data?: T; error?: string };
  if (!resp.ok) throw new Error(resp.error ?? `HTTP ${resp.status}`);
  return resp.data as T;
}
