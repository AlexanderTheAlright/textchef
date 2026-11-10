"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Contrast } from "@/components/Contrast";
import { Filters } from "@/components/Filters";
import { HitCard } from "@/components/HitCard";
import { LogoMark } from "@/components/LogoMark";
import { TopicMap } from "@/components/TopicMap";
import { TopicPanel } from "@/components/TopicPanel";
import { api } from "@/lib/api";
import { applyTheme, prefersDark, savedTheme, saveTheme } from "@/lib/theme";
import type {
  ContrastResult, Facets, Graph, Hit, QueryResult, Scope, Status, Theme, TopicDetail,
} from "@/lib/types";

type Tab = "texts" | "map" | "contrast";

// what the text list is currently showing
type Listing =
  | { kind: "none" }
  | { kind: "query"; q: string; data: QueryResult }
  | { kind: "similar"; source: Hit; hits: Hit[] }
  | { kind: "random"; hits: Hit[] }
  | { kind: "browse"; hits: Hit[]; total: number }
  | { kind: "document"; id: string; hits: Hit[] };

export default function Page() {
  const [status, setStatus] = useState<Status | null>(null);
  const [themes, setThemes] = useState<Theme[]>([]);
  const [themeName, setThemeName] = useState("");
  const [graph, setGraph] = useState<Graph | null>(null);
  const [facets, setFacets] = useState<Facets | null>(null);
  const [scope, setScope] = useState<Scope>({});
  const [tab, setTab] = useState<Tab>("texts");
  const [q, setQ] = useState("");
  const [listing, setListing] = useState<Listing>({ kind: "none" });
  const [topic, setTopic] = useState<TopicDetail | null>(null);
  const [contrast, setContrast] = useState<ContrastResult | null>(null);
  const [error, setError] = useState("");

  const guard = useCallback(async (work: () => Promise<void>) => {
    try { setError(""); await work(); } catch (e) { setError(String(e)); }
  }, []);

  useEffect(() => {
    guard(async () => {
      const [s, t, g] = await Promise.all([api.status(), api.themes(), api.graph()]);
      setStatus(s);
      setThemes(t.themes);
      setGraph(g);
      const names = t.themes.map((x) => x.name);
      // ?theme= &q= &topic= &tab= open the page in a given state
      const url = new URLSearchParams(window.location.search);
      const wanted = [url.get("theme"), savedTheme(), prefersDark() ? s.theme_dark : s.theme_light];
      setThemeName(wanted.find((n) => n && names.includes(n)) ?? names[0]);
      const query = url.get("q");
      if (query) {
        setQ(query);
        setListing({ kind: "query", q: query, data: await api.query(query, {}) });
      }
      const topicId = Number(url.get("topic") ?? NaN);
      if (Number.isInteger(topicId)) setTopic(await api.topic(topicId, {}));
      const wantedTab = url.get("tab");
      if (wantedTab === "map" || wantedTab === "contrast" || wantedTab === "texts") setTab(wantedTab);
      else if (Number.isInteger(topicId)) setTab("map");
    });
  }, [guard]);

  const theme = useMemo(() => themes.find((t) => t.name === themeName) ?? null, [themes, themeName]);
  useEffect(() => { if (theme) applyTheme(theme); }, [theme]);

  // filter counts follow the scope; an open query or browse reruns inside it
  useEffect(() => {
    guard(async () => {
      setFacets(await api.facets(scope));
      if (listing.kind === "query") setListing({ kind: "query", q: listing.q, data: await api.query(listing.q, scope) });
      if (listing.kind === "browse") {
        const b = await api.browse(scope, 0);
        setListing({ kind: "browse", hits: b.results, total: b.total });
      }
      if (topic) setTopic(await api.topic(topic.id, scope));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope]);

  const search = (text: string) => guard(async () => {
    if (!text.trim()) return;
    setQ(text);
    setListing({ kind: "query", q: text, data: await api.query(text, scope) });
    setTab("texts");
  });
  const similar = (hit: Hit) => guard(async () => {
    const r = await api.similar(hit.row);
    setListing({ kind: "similar", source: r.source, hits: r.results });
    setTab("texts");
  });
  const random = () => guard(async () => {
    setListing({ kind: "random", hits: (await api.random(scope)).results });
    setTab("texts");
  });
  const browse = () => guard(async () => {
    const b = await api.browse(scope, 0);
    setListing({ kind: "browse", hits: b.results, total: b.total });
    setTab("texts");
  });
  const more = () => guard(async () => {
    if (listing.kind !== "browse") return;
    const b = await api.browse(scope, listing.hits.length);
    setListing({ ...listing, hits: [...listing.hits, ...b.results] });
  });
  const openDocument = (hit: Hit) => guard(async () => {
    const d = await api.document(hit.row);
    setListing({ kind: "document", id: d.id, hits: d.results });
    setTab("texts");
  });
  const openTopic = (id: number) => guard(async () => {
    setTopic(await api.topic(id, scope));
    setTab("map");
  });

  if (!status || !theme || !graph || !facets) {
    return <main className="loading">{error || "…"}</main>;
  }

  const lift = contrast && !contrast.too_few
    ? Object.fromEntries(contrast.lift.map((l) => [l.id, l.lift])) : null;
  const topicLabel = (id: number) => graph.topics.find((t) => t.id === id)?.label ?? String(id);
  const cards = (hits: Hit[]) => hits.map((h) => (
    <HitCard key={h.row} hit={h} status={status} facets={facets}
      onSimilar={similar} onDocument={openDocument} onTopic={openTopic} />
  ));
  const map = (
    <TopicMap graph={graph} theme={theme} counts={facets.topics} lift={lift}
      selected={topic?.id ?? null} onSelect={openTopic} />
  );

  return (
    <div className="app">
      <header className="top">
        <h1><LogoMark />{theme.strings.title}</h1>
        <span className="top-meta">
          {status.n_rows.toLocaleString()} texts · {status.n_topics} topics
        </span>
        <span className="spacer" />
        <label className="theme-pick">
          Theme
          <select value={themeName}
            onChange={(e) => { setThemeName(e.target.value); saveTheme(e.target.value); }}>
            {themes.map((t) => <option key={t.name} value={t.name}>{t.label}</option>)}
          </select>
        </label>
      </header>

      <div className="body">
        <Filters facets={facets} scope={scope} onChange={setScope} />

        <main className="main">
          <form className="searchbar" onSubmit={(e) => { e.preventDefault(); search(q); }}>
            <input value={q} onChange={(e) => setQ(e.target.value)} aria-label="Query"
              placeholder={theme.strings.search_placeholder} />
            <button className="primary" type="submit">Search</button>
            <button type="button" onClick={random}>Random</button>
            <button type="button" onClick={browse}>Browse</button>
          </form>

          <nav className="tabs">
            {(["texts", "map", "contrast"] as Tab[]).map((t) => (
              <button key={t} className={tab === t ? "tab on" : "tab"} onClick={() => setTab(t)}>
                {t === "texts" ? "Texts" : t === "map" ? "Map" : "Contrast"}
              </button>
            ))}
            {(scope.topics ?? []).map((id) => (
              <span className="chip strong" key={id}>
                {topicLabel(id)}
                <button className="chip-x" aria-label="Remove topic filter"
                  onClick={() => setScope({ ...scope, topics: scope.topics!.filter((x) => x !== id) })}>×</button>
              </span>
            ))}
          </nav>
          {error && <p className="error">{error}</p>}

          {tab === "texts" && (
            <section className="list">
              {listing.kind === "none" && <p className="empty">{theme.strings.start}</p>}
              {listing.kind === "query" && (
                <>
                  <div className="row">
                    <span className="count">
                      {listing.data.total_matched.toLocaleString()} of {listing.data.n_in_scope.toLocaleString()}
                    </span>
                    {listing.data.terms.map((t, i) => (
                      <span className="chip mark" key={i} title={t.fuzzy ? "Closest known word" : "Matched"}>
                        {t.term}
                      </span>
                    ))}
                  </div>
                  {listing.data.topic_hits.length > 0 && (
                    <div className="row">
                      <span className="label">Topics</span>
                      {listing.data.topic_hits.slice(0, 6).map((t) => (
                        <button className="link" key={t.id} onClick={() => openTopic(t.id)}>
                          {t.label} ({t.n})
                        </button>
                      ))}
                    </div>
                  )}
                  {listing.data.results.length ? cards(listing.data.results)
                    : <p className="empty">{theme.strings.empty}</p>}
                </>
              )}
              {listing.kind === "similar" && (
                <>
                  <div className="row"><span className="label">Similar to</span></div>
                  <div className="source">{cards([listing.source])}</div>
                  {cards(listing.hits)}
                </>
              )}
              {listing.kind === "random" && (listing.hits.length ? cards(listing.hits)
                : <p className="empty">{theme.strings.empty}</p>)}
              {listing.kind === "browse" && (
                <>
                  <div className="row">
                    <span className="count">{listing.hits.length.toLocaleString()} of {listing.total.toLocaleString()}</span>
                  </div>
                  {listing.hits.length ? cards(listing.hits) : <p className="empty">{theme.strings.empty}</p>}
                  {listing.hits.length < listing.total && <button onClick={more}>More</button>}
                </>
              )}
              {listing.kind === "document" && (
                <>
                  <div className="row"><span className="label">{status.id_label}</span><span className="count">{listing.id}</span></div>
                  {cards(listing.hits)}
                </>
              )}
            </section>
          )}

          {tab === "map" && (
            <section className={topic ? "map-view split" : "map-view"}>
              {map}
              {topic && (
                <TopicPanel detail={topic} onTopic={openTopic} onClose={() => setTopic(null)}
                  onFilter={(id) => setScope({ ...scope, topics: [id] })}>
                  {topic.results.length ? cards(topic.results) : <p className="empty">{theme.strings.empty}</p>}
                </TopicPanel>
              )}
            </section>
          )}

          {tab === "contrast" && (
            <section className="contrast-view">
              <Contrast facets={facets} scope={scope} onResult={setContrast} onSearch={search} />
              {lift && map}
            </section>
          )}
        </main>
      </div>
    </div>
  );
}
