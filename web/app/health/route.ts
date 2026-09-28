import { NextResponse } from "next/server";

import pkg from "../../package.json";

export function GET() {
  return NextResponse.json(
    {
      status: "ok",
      service: "taal-web",
      version: pkg.version,
      api_base: process.env.NEXT_PUBLIC_TAAL_API_URL ?? "http://localhost:8080",
    },
    { headers: { "Cache-Control": "no-store" } },
  );
}
