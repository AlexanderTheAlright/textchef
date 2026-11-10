"use client";

import type { ReactNode } from "react";
import type { TopicDetail } from "@/lib/types";

type Props = {
  detail: TopicDetail;
  onTopic: (id: number) => void;
  onFilter: (id: number) => void;
  onClose: () => void;
  children: ReactNode;      // the topic's texts, rendered by the page
};

export function TopicPanel({ detail, onTopic, onFilter, onClose, children }: Props) {
  return (
    <section className="panel">
      <header className="panel-head">
        <h2>{detail.label}</h2>
        <span className="count">{detail.n_in_scope.toLocaleString()} / {detail.count.toLocaleString()}</span>
        <span className="spacer" />
        <button className="link" onClick={() => onFilter(detail.id)}>Filter to topic</button>
        <button className="link" onClick={onClose} aria-label="Close">Close</button>
      </header>
      <div className="chips">
        {detail.keywords.map((k) => <span className="chip" key={k}>{k}</span>)}
      </div>
      {detail.neighbours.length > 0 && (
        <div className="row">
          <span className="label">Near</span>
          {detail.neighbours.map((n) => (
            <button className="link" key={n.id} onClick={() => onTopic(n.id)}>{n.label}</button>
          ))}
        </div>
      )}
      <div className="breakdown">
        {Object.entries(detail.breakdown).map(([column, b]) => b.values.length > 0 && (
          <table key={column}>
            <thead><tr><th>{b.label}</th><th>n</th><th title="Share in topic over share overall">lift</th></tr></thead>
            <tbody>
              {b.values.slice(0, 5).map((v) => (
                <tr key={v.v}><td title={v.v}>{v.v}</td><td>{v.n}</td><td>{v.lift?.toFixed(2) ?? ""}</td></tr>
              ))}
            </tbody>
          </table>
        ))}
      </div>
      {children}
    </section>
  );
}
