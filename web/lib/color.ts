/** Blend two hex colours; t = 0 gives a, t = 1 gives b. */
export function mix(a: string, b: string, t: number): string {
  const pa = parse(a), pb = parse(b);
  const c = pa.map((v, i) => Math.round(v + (pb[i] - v) * t));
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}

function parse(hex: string): number[] {
  let h = hex.slice(1);
  if (h.length < 6) h = [...h.slice(0, 3)].map((ch) => ch + ch).join("");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
}
