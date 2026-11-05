import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // On Vercel the API is served from the same domain under /api, so the client uses relative URLs.
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? (process.env.VERCEL ? "" : "http://127.0.0.1:8000"),
  },
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
