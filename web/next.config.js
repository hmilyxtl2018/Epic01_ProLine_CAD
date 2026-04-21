/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The Dashboard backend lives at NEXT_PUBLIC_API_BASE (set in .env.local).
  // We rewrite /api/* in the dev server to that origin so the browser stays
  // same-origin and doesn't need CORS during local development.
  async rewrites() {
    const target = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${target}/:path*` }];
  },
};

module.exports = nextConfig;
