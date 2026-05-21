/** @type {import('next').NextConfig} */

// API origin the browser will fetch from — must be in CSP's `connect-src`.
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// CSP — matches the API layer for symmetry. Tighten as inline scripts are removed.
const csp = [
  "default-src 'self'",
  "img-src 'self' data: blob: https:",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "font-src 'self' https://fonts.gstatic.com data:",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval'", // Next.js dev needs unsafe-eval; tighten in prod via env-driven config
  `connect-src 'self' ${API_URL}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
  "worker-src 'self' blob:",
].join("; ");

const securityHeaders = [
  { key: "X-Frame-Options",          value: "DENY" },
  { key: "X-Content-Type-Options",   value: "nosniff" },
  { key: "Referrer-Policy",          value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy",
    value: "accelerometer=(), autoplay=(), camera=(), display-capture=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), midi=(), payment=(), usb=(), xr-spatial-tracking=()" },
  { key: "Content-Security-Policy",  value: csp },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  { key: "X-Permitted-Cross-Domain-Policies", value: "none" },
];

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Tree-shake barrel-file packages so importing 3 icons from lucide-react doesn't pull the
  // whole icon set into the route bundle. Cuts per-route JS noticeably with zero code changes.
  experimental: {
    optimizePackageImports: ["lucide-react"],
  },
  async headers() {
    return [{ source: "/(.*)", headers: securityHeaders }];
  },
};

export default nextConfig;
