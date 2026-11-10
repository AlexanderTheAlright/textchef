"use client";

import type { Facets, Hit, Status } from "@/lib/types";

type Props = {
  hit: Hit;
  status: Status;
  facets: Facets;
  onSimilar: (hit: Hit) => void;
  onDocument: (hit: Hit) => void;
  onTopic: (id: number) => void;
};

function hostOf(url: string): string {
  try { return new URL(url).hostname; } catch { return "Source"; }
}

export function HitCard({ hit, status, facets, onSimilar, onDocument, onTopic }: Props) {
  const chips = Object.entries(hit.facets).filter(([, v]) => v !== null && v !== "");
  return (
    <article className="hit">
      <p className="hit-text">{hit.text}</p>
      <div className="chips">
        {hit.group && <span className="chip strong" title={status.group_label}>{hit.group}</span>}
        {chips.map(([column, value]) => (
          <span className="chip" key={column} title={facets.facets[column]?.label ?? column}>
            {String(value)}
          </span>
        ))}
      </div>
      <div className="hit-foot">
        {hit.score !== undefined && <span className="score" title="Score">{hit.score.toFixed(2)}</span>}
        {(hit.n_same ?? 1) > 1 && <span className="count" title="Texts with this wording">×{hit.n_same}</span>}
        {hit.topic_label && (
          <button className="link" onClick={() => onTopic(hit.topic)}>{hit.topic_label}</button>
        )}
        <span className="spacer" />
        {hit.credit && (hit.credit_url
          ? <a className="credit" href={hit.credit_url} target="_blank" rel="noopener noreferrer">{hit.credit}</a>
          : <span className="credit">{hit.credit}</span>)}
        {hit.url && <a href={hit.url} target="_blank" rel="noopener noreferrer">{hostOf(hit.url)}</a>}
        {hit.id !== undefined && <span className="count" title={status.id_label}>{hit.id}</span>}
        {(hit.n_id ?? 1) > 1 && (
          <button className="link" onClick={() => onDocument(hit)}>
            {status.id_label} ({hit.n_id})
          </button>
        )}
        <button className="link" onClick={() => onSimilar(hit)}>Similar</button>
      </div>
    </article>
  );
}
