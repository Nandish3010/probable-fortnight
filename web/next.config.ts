import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Always define the mock flag at build time. Unset, `process.env.NEXT_PUBLIC_TAAL_MOCK` is only
  // known at run time, the bundler cannot fold it, and every mock fixture ships in the client
  // bundle (the Cloud Run image builds without setting it; infra/Dockerfile.web). Defined as "0",
  // the mock branches are dropped from a production build; `NEXT_PUBLIC_TAAL_MOCK=1` still wins.
  env: { NEXT_PUBLIC_TAAL_MOCK: process.env.NEXT_PUBLIC_TAAL_MOCK ?? "0" },
};

export default nextConfig;
