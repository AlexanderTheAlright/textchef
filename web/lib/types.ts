export type Range = { min?: string | number | null; max?: string | number | null };
export type Scope = {
  groups?: string[];
  topics?: number[];
  filters?: Record<string, string[] | Range>;
};

export type Status = {
  n_rows: number;
  n_unique: number;
  n_topics: number;
  model: string;
  has_id: boolean;
  has_group: boolean;
  group_label: string;
  id_label: string;
  theme_light: string;
  theme_dark: string;
};

export type Theme = {
  name: string;
  label: string;
  scheme: "light" | "dark";
  font: string;
  font_mono: string;
  colors: Record<string, string>;
  graph: { edge: string; label: string; muted: string; lift_low: string; lift_high: string; palette: string[] };
  strings: { title: string; search_placeholder: string; start: string; empty: string };
};

export type Hit = {
  row: number;
  id?: string;
  n_id?: number;
  text: string;
  words: number;
  topic: number;
  topic_label: string | null;
  group?: string | null;
  facets: Record<string, string | number | null>;
  score?: number;
  wording?: number;
  n_same?: number;
  url?: string | null;
  credit?: string | null;
  credit_url?: string | null;
};

export type FacetValue = { v: string; n: number };
export type FacetInfo = {
  label: string;
  type: "categorical" | "numeric" | "date";
  contrast: boolean;
  coverage: number;
  values?: FacetValue[];
  min?: string | number | null;
  max?: string | number | null;
};
export type Facets = { n: number; facets: Record<string, FacetInfo>; topics: Record<string, number> };

export type Topic = { id: number; label: string; count: number; macro: number; x: number; y: number };
export type Graph = {
  topics: Topic[];
  edges: { a: number; b: number; w: number }[];
  macro_labels: Record<string, string>;
  points: [number, number, number][];
};

export type QueryResult = {
  method: string;
  terms: { term: string; fuzzy: boolean }[];
  results: Hit[];
  total_matched: number;
  n_in_scope: number;
  topic_hits: { id: number; n: number; label: string }[];
};

export type TopicDetail = {
  id: number;
  label: string;
  keywords: string[];
  count: number;
  n_in_scope: number;
  macro_label: string;
  neighbours: { id: number; label: string; sim: number }[];
  breakdown: Record<string, { label: string; values: { v: string; n: number; lift: number | null }[] }>;
  results: Hit[];
};

export type ContrastWord = { w: string; z: number; rate_a: number; rate_b: number };
export type ContrastResult = {
  n_a: number;
  n_b: number;
  words_a: ContrastWord[];
  words_b: ContrastWord[];
  lift: { id: number; lift: number; n: number }[];
  too_few: boolean;
};
