"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { mix } from "@/lib/color";
import type { Graph, Theme } from "@/lib/types";

type Props = {
  graph: Graph;
  theme: Theme;
  counts: Record<string, number>;          // texts per topic inside the current filters
  lift: Record<number, number> | null;     // contrast shading, when a contrast is shown
  selected: number | null;
  onSelect: (id: number) => void;
};

type View = { k: number; x: number; y: number };
type Box = { x: number; y: number; w: number; h: number };
type Label = Box & { id: number; text: string };

const FONT_PX = 12;
const LABEL_H = 16;
const LABEL_MAX_W = 190;
const GAP = 4;            // between a node and its label
const MARGIN = 3;         // kept clear around every label
const MAX_R = 16;

const radius = (n: number, max: number) => 4 + (MAX_R - 4) * Math.sqrt(n / max);

function boxesTouch(a: Box, b: Box): boolean {
  return a.x < b.x + b.w + MARGIN && b.x < a.x + a.w + MARGIN
    && a.y < b.y + b.h + MARGIN && b.y < a.y + a.h + MARGIN;
}

function boxTouchesCircle(b: Box, cx: number, cy: number, r: number): boolean {
  const dx = cx - Math.max(b.x, Math.min(cx, b.x + b.w));
  const dy = cy - Math.max(b.y, Math.min(cy, b.y + b.h));
  return dx * dx + dy * dy < (r + MARGIN) * (r + MARGIN);
}

export function TopicMap({ graph, theme, counts, lift, selected, onSelect }: Props) {
  const frame = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [view, setView] = useState<View>({ k: 1, x: 0, y: 0 });
  const [hover, setHover] = useState<number | null>(null);
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);

  // the drawing is laid out in CSS pixels, so label text keeps its size
  useEffect(() => {
    const el = frame.current!;
    const measure = () => {
      const w = el.clientWidth;
      setSize({ w, h: Math.round(Math.max(260, Math.min(w * 0.62, window.innerHeight * 0.7))) });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    window.addEventListener("resize", measure);
    return () => { observer.disconnect(); window.removeEventListener("resize", measure); };
  }, []);

  // ?zoom=N opens the map zoomed about its centre
  useEffect(() => {
    const k = Number(new URLSearchParams(window.location.search).get("zoom"));
    if (size.w && k > 1 && k <= 12) setView({ k, x: (size.w / 2) * (1 - k), y: (size.h / 2) * (1 - k) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size.w > 0]);

  const maxCount = Math.max(...graph.topics.map((t) => t.count), 1);

  // data coordinates -> pixels at zoom 1: every topic node fits inside the frame
  const base = useMemo(() => {
    const xs = graph.topics.map((t) => t.x), ys = graph.topics.map((t) => t.y);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const pad = MAX_R + 28;
    return (x: number, y: number): [number, number] => [
      pad + ((x - x0) / (x1 - x0 || 1)) * (size.w - 2 * pad),
      size.h - pad - ((y - y0) / (y1 - y0 || 1)) * (size.h - 2 * pad),
    ];
  }, [graph, size]);

  const place = (x: number, y: number): [number, number] => {
    const [bx, by] = base(x, y);
    return [bx * view.k + view.x, by * view.k + view.y];
  };

  // largest first, so a small node is never drawn under a big one
  const nodes = useMemo(() => [...graph.topics].sort((a, b) => b.count - a.count).map((t) => {
    const [bx, by] = base(t.x, t.y);
    return { ...t, cx: bx * view.k + view.x, cy: by * view.k + view.y, r: radius(t.count, maxCount) };
  }), [graph, base, view, maxCount]);

  const textWidth = useMemo(() => {
    const ctx = typeof document === "undefined" ? null : document.createElement("canvas").getContext("2d");
    if (ctx) ctx.font = `${FONT_PX}px ${theme.font}`;
    return (s: string) => (ctx ? ctx.measureText(s).width : s.length * 7) + 2;
  }, [theme.font]);

  // A label is drawn only where its box touches no other label and no node.
  // Bigger topics choose first; the rest show on hover or after zooming in.
  const labels = useMemo(() => {
    const placed: Label[] = [];
    if (!size.w) return placed;
    for (const n of nodes) {
      if (n.cx < 0 || n.cx > size.w || n.cy < 0 || n.cy > size.h) continue;
      const terms = n.label.split(", ");
      let text = terms.join(", ");
      while (terms.length > 1 && textWidth(text) > LABEL_MAX_W) { terms.pop(); text = terms.join(", "); }
      const w = textWidth(text);
      if (w > LABEL_MAX_W) continue;
      const spots: [number, number][] = [
        [n.cx - w / 2, n.cy - n.r - GAP - LABEL_H],
        [n.cx - w / 2, n.cy + n.r + GAP],
        [n.cx + n.r + GAP, n.cy - LABEL_H / 2],
        [n.cx - n.r - GAP - w, n.cy - LABEL_H / 2],
      ];
      for (const [x, y] of spots) {
        const box = { x, y, w, h: LABEL_H };
        if (x < MARGIN || y < MARGIN || x + w > size.w - MARGIN || y + LABEL_H > size.h - MARGIN) continue;
        if (placed.some((p) => boxesTouch(box, p))) continue;
        if (nodes.some((m) => boxTouchesCircle(box, m.cx, m.cy, m.r))) continue;
        placed.push({ ...box, id: n.id, text });
        break;
      }
    }
    return placed;
  }, [nodes, size, textWidth]);

  const palette = theme.graph.palette;
  const fill = (id: number, macro: number): string => {
    if ((counts[id] ?? 0) === 0) return theme.graph.muted;
    if (lift) {
      const l = lift[id];
      if (l === undefined) return theme.graph.muted;
      const t = Math.max(-1, Math.min(1, Math.log2(Math.max(l, 0.01))));
      return mix(theme.graph.muted, t > 0 ? theme.graph.lift_high : theme.graph.lift_low, Math.abs(t));
    }
    return palette[macro % palette.length];
  };
  const macroOf = useMemo(() => new Map(graph.topics.map((t) => [t.id, t.macro])), [graph]);
  const at = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  const zoom = (factor: number, cx = size.w / 2, cy = size.h / 2) =>
    setView((v) => {
      const k = Math.max(1, Math.min(12, v.k * factor));
      const f = k / v.k;
      return { k, x: cx - (cx - v.x) * f, y: cy - (cy - v.y) * f };
    });
  const local = (e: { clientX: number; clientY: number }): [number, number] => {
    const r = frame.current!.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  };

  const hovered = hover !== null && !labels.some((l) => l.id === hover) ? at.get(hover) : undefined;
  const hoverW = hovered ? textWidth(hovered.label) + 8 : 0;

  return (
    <div className="map-wrap">
      <div className="map-tools">
        {lift && (
          <span className="map-legend">
            <span className="swatch lift-low" /> B
            <span className="swatch lift-high" /> A
          </span>
        )}
        <span className="spacer" />
        <button onClick={() => zoom(1.5)} aria-label="Zoom in">+</button>
        <button onClick={() => zoom(1 / 1.5)} aria-label="Zoom out">−</button>
        <button onClick={() => setView({ k: 1, x: 0, y: 0 })}>Reset</button>
      </div>
      <div className="map" ref={frame}>
      {size.w > 0 && (
        <svg width={size.w} height={size.h} role="img" aria-label="Topic map" data-zoom={view.k}
          onWheel={(e) => { const [cx, cy] = local(e); zoom(e.deltaY < 0 ? 1.2 : 1 / 1.2, cx, cy); }}
          onPointerDown={(e) => { drag.current = { x: e.clientX, y: e.clientY, moved: false }; }}
          onPointerMove={(e) => {
            const d = drag.current;
            if (!d) return;
            const dx = e.clientX - d.x, dy = e.clientY - d.y;
            if (Math.abs(dx) + Math.abs(dy) > 2) d.moved = true;
            d.x = e.clientX; d.y = e.clientY;
            setView((v) => ({ ...v, x: v.x + dx, y: v.y + dy }));
          }}
          onPointerUp={() => { window.setTimeout(() => { drag.current = null; }, 0); }}
          onPointerLeave={() => { drag.current = null; }}>
          <g className="map-edges">
            {graph.edges.map((e) => {
              const a = at.get(e.a), b = at.get(e.b);
              return a && b && <line key={`${e.a}-${e.b}`} x1={a.cx} y1={a.cy} x2={b.cx} y2={b.cy}
                stroke={theme.graph.edge} strokeWidth={1} opacity={0.3} />;
            })}
          </g>
          <g className="map-points">
            {graph.points.map((p, i) => {
              const [x, y] = place(p[0], p[1]);
              return <circle key={i} cx={x} cy={y} r={1.2} opacity={0.3}
                fill={p[2] < 0 ? theme.graph.muted : fill(p[2], macroOf.get(p[2]) ?? 0)} />;
            })}
          </g>
          {nodes.map((n) => (
            <circle key={n.id} className="topic-dot" data-node={n.id} cx={n.cx} cy={n.cy} r={n.r}
              fill={fill(n.id, n.macro)} fillOpacity={0.8}
              stroke={n.id === selected ? theme.graph.label : theme.colors.surface}
              strokeWidth={n.id === selected ? 2.5 : 1}
              onPointerEnter={() => setHover(n.id)} onPointerLeave={() => setHover(null)}
              onClick={() => { if (!drag.current?.moved) onSelect(n.id); }} />
          ))}
          {labels.map((l) => (
            <text key={l.id} data-label={l.id} x={l.x + 1} y={l.y + FONT_PX} fontSize={FONT_PX}
              fill={theme.graph.label} stroke={theme.colors.surface} strokeWidth={3}
              paintOrder="stroke" pointerEvents="none">{l.text}</text>
          ))}
          {hovered && (
            <g data-hover pointerEvents="none" transform={`translate(${
              Math.max(2, Math.min(size.w - hoverW - 2, hovered.cx - hoverW / 2))} ${
              hovered.cy - hovered.r - GAP - LABEL_H - 4 < 2 ? hovered.cy + hovered.r + GAP : hovered.cy - hovered.r - GAP - LABEL_H - 4})`}>
              <rect width={hoverW} height={LABEL_H + 4} rx={4} fill={theme.colors.surface_alt}
                stroke={theme.colors.border} />
              <text x={4} y={FONT_PX + 2} fontSize={FONT_PX} fill={theme.graph.label}>{hovered.label}</text>
            </g>
          )}
        </svg>
      )}
      </div>
    </div>
  );
}
