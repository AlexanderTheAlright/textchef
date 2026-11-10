"use client";

import { useState } from "react";
import type { FacetInfo, Facets, Range, Scope } from "@/lib/types";

type Props = { facets: Facets; scope: Scope; onChange: (scope: Scope) => void };

const SHOWN = 8;

export function selectedValues(scope: Scope, column: string): string[] {
  if (column === "group") return scope.groups ?? [];
  const v = scope.filters?.[column];
  return Array.isArray(v) ? v : [];
}

export function withValues(scope: Scope, column: string, values: string[]): Scope {
  if (column === "group") return { ...scope, groups: values };
  const filters = { ...(scope.filters ?? {}) };
  if (values.length) filters[column] = values;
  else delete filters[column];
  return { ...scope, filters };
}

function withRange(scope: Scope, column: string, range: Range): Scope {
  const filters = { ...(scope.filters ?? {}) };
  if (range.min || range.max) filters[column] = range;
  else delete filters[column];
  return { ...scope, filters };
}

export function scopeIsEmpty(scope: Scope): boolean {
  return !scope.groups?.length && !scope.topics?.length && !Object.keys(scope.filters ?? {}).length;
}

function Categorical({ column, info, scope, onChange }: {
  column: string; info: FacetInfo; scope: Scope; onChange: (s: Scope) => void;
}) {
  const [find, setFind] = useState("");
  const [all, setAll] = useState(false);
  const chosen = selectedValues(scope, column);
  const values = (info.values ?? []).filter(
    (v) => !find || v.v.toLowerCase().includes(find.toLowerCase()));
  const shown = all || find ? values.slice(0, 200) : values.slice(0, SHOWN);
  const toggle = (v: string) =>
    onChange(withValues(scope, column,
      chosen.includes(v) ? chosen.filter((x) => x !== v) : [...chosen, v]));
  return (
    <>
      {(info.values?.length ?? 0) > SHOWN && (
        <input className="facet-find" value={find} placeholder="Find"
          aria-label={`Find in ${info.label}`} onChange={(e) => setFind(e.target.value)} />
      )}
      <ul className="facet-values">
        {shown.map((v) => (
          <li key={v.v}>
            <label title={v.v}>
              <input type="checkbox" checked={chosen.includes(v.v)} onChange={() => toggle(v.v)} />
              <span className="facet-value">{v.v}</span>
              <span className="count">{v.n.toLocaleString()}</span>
            </label>
          </li>
        ))}
      </ul>
      {!find && values.length > SHOWN && (
        <button className="link" onClick={() => setAll(!all)}>
          {all ? "Fewer" : `All ${values.length}`}
        </button>
      )}
    </>
  );
}

function RangeInputs({ column, info, scope, onChange }: {
  column: string; info: FacetInfo; scope: Scope; onChange: (s: Scope) => void;
}) {
  const current = scope.filters?.[column];
  const range: Range = current && !Array.isArray(current) ? current : {};
  const type = info.type === "date" ? "date" : "number";
  const set = (key: "min" | "max", value: string) =>
    onChange(withRange(scope, column, { ...range, [key]: value || null }));
  return (
    <div className={`facet-range ${type}`}>
      <input type={type} aria-label={`${info.label} from`} value={range.min ?? ""}
        placeholder={String(info.min ?? "")} min={info.min ?? undefined} max={info.max ?? undefined}
        onChange={(e) => set("min", e.target.value)} />
      <span>–</span>
      <input type={type} aria-label={`${info.label} to`} value={range.max ?? ""}
        placeholder={String(info.max ?? "")} min={info.min ?? undefined} max={info.max ?? undefined}
        onChange={(e) => set("max", e.target.value)} />
    </div>
  );
}

export function Filters({ facets, scope, onChange }: Props) {
  return (
    <aside className="filters">
      <div className="filters-head">
        <span>{facets.n.toLocaleString()} texts</span>
        {!scopeIsEmpty(scope) && (
          <button className="link" onClick={() => onChange({})}>Clear</button>
        )}
      </div>
      {Object.entries(facets.facets).map(([column, info]) => (
        <details key={column} className="facet" open={column === "group" || info.type !== "categorical"}>
          <summary>{info.label}</summary>
          {info.type === "categorical"
            ? <Categorical column={column} info={info} scope={scope} onChange={onChange} />
            : <RangeInputs column={column} info={info} scope={scope} onChange={onChange} />}
        </details>
      ))}
    </aside>
  );
}
