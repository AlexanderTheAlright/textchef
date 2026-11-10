"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ContrastResult, ContrastWord, Facets, Scope } from "@/lib/types";
import { withValues } from "./Filters";

type Props = {
  facets: Facets;
  scope: Scope;                                   // the current filters; the contrast runs inside them
  onResult: (r: ContrastResult | null) => void;   // shades the map
  onSearch: (word: string) => void;
};

const REST = "";

function Words({ title, n, words, side, onSearch }: {
  title: string; n: number; words: ContrastWord[]; side: "a" | "b"; onSearch: (w: string) => void;
}) {
  return (
    <table className="contrast-words">
      <thead>
        <tr><th>{title} <span className="count">{n.toLocaleString()}</span></th><th>A %</th><th>B %</th></tr>
      </thead>
      <tbody>
        {words.map((w) => (
          <tr key={w.w}>
            <td><button className={`link word-${side}`} onClick={() => onSearch(w.w)}>{w.w}</button></td>
            <td>{(w.rate_a * 100).toFixed(1)}</td>
            <td>{(w.rate_b * 100).toFixed(1)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Contrast({ facets, scope, onResult, onSearch }: Props) {
  const columns = Object.entries(facets.facets).filter(
    ([, f]) => f.type === "categorical" && f.contrast && (f.values?.length ?? 0) > 1);
  const [column, setColumn] = useState(columns[0]?.[0] ?? "");
  const [a, setA] = useState("");
  const [b, setB] = useState(REST);
  const [result, setResult] = useState<ContrastResult | null>(null);
  const [busy, setBusy] = useState(false);
  const values = facets.facets[column]?.values ?? [];

  const run = async (col = column, va = a, vb = b) => {
    if (!va) return;
    setBusy(true);
    try {
      // the contrasted facet is dropped from the surrounding filters
      const within = withValues(scope, col, []);
      const r = await api.contrast(withValues({}, col, [va]),
        vb === REST ? null : withValues({}, col, [vb]), within);
      setResult(r);
      onResult(r);
    } finally {
      setBusy(false);
    }
  };

  // ?contrast=column:value opens with that contrast run
  useEffect(() => {
    const [col, ...rest] = (new URLSearchParams(window.location.search).get("contrast") ?? "").split(":");
    const value = rest.join(":");
    if (columns.some(([c]) => c === col) && value) {
      setColumn(col);
      setA(value);
      void run(col, value, REST);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!columns.length) return <p className="empty">No facet to contrast</p>;
  return (
    <section className="contrast">
      <div className="row">
        <select aria-label="Facet" value={column}
          onChange={(e) => { setColumn(e.target.value); setA(""); setB(REST); }}>
          {columns.map(([c, f]) => <option key={c} value={c}>{f.label}</option>)}
        </select>
        <select aria-label="A" value={a} onChange={(e) => setA(e.target.value)}>
          <option value="">A</option>
          {values.map((v) => <option key={v.v} value={v.v}>{v.v} ({v.n})</option>)}
        </select>
        <span className="label">vs</span>
        <select aria-label="B" value={b} onChange={(e) => setB(e.target.value)}>
          <option value={REST}>Everything else</option>
          {values.filter((v) => v.v !== a).map((v) => <option key={v.v} value={v.v}>{v.v} ({v.n})</option>)}
        </select>
        <button className="primary" disabled={!a || busy} onClick={() => run()}>Contrast</button>
        {result && (
          <button className="link" onClick={() => { setResult(null); onResult(null); }}>Clear</button>
        )}
      </div>
      {result?.too_few && <p className="empty">Too few texts on one side</p>}
      {result && !result.too_few && (
        <div className="contrast-tables">
          <Words title={a} n={result.n_a} words={result.words_a} side="a" onSearch={onSearch} />
          <Words title={b === REST ? "Everything else" : b} n={result.n_b} words={result.words_b}
            side="b" onSearch={onSearch} />
        </div>
      )}
    </section>
  );
}
