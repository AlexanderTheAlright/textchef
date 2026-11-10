import type { NextConfig } from "next";

// A static export: the Python server serves web/out, so there is no Node server.
const config: NextConfig = { output: "export", images: { unoptimized: true } };

export default config;
