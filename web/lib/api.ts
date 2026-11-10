import type {
  ContrastResult, Facets, Graph, Hit, QueryResult, Scope, Status, Theme, TopicDetail,
} from "./types";

async function call<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, body === undefined ? undefined : {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json() as Promise<T>;
}

export const api = {
  status: () => call<Status>("/status"),
  themes: () => call<{ themes: Theme[] }>("/themes"),
  graph: () => call<Graph>("/graph"),
  facets: (scope: Scope) => call<Facets>("/facets", { scope }),
  query: (q: string, scope: Scope) => call<QueryResult>("/query", { q, k: 60, scope }),
  similar: (row: number) => call<{ source: Hit; results: Hit[] }>("/similar", { row, k: 20 }),
  random: (scope: Scope) => call<{ results: Hit[]; n_in_scope: number }>("/random", { n: 10, scope }),
  browse: (scope: Scope, offset: number) =>
    call<{ results: Hit[]; total: number; offset: number }>("/browse", { scope, offset, limit: 50 }),
  topic: (id: number, scope: Scope) => call<TopicDetail>(`/topic/${id}`, { scope }),
  contrast: (a: Scope, b: Scope | null, within: Scope) =>
    call<ContrastResult>("/contrast", { a, b, within }),
  document: (row: number) => call<{ id: string; n: number; results: Hit[] }>(`/document/${row}`),
};
