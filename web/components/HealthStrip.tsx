"use client";

import { useEffect, useState } from "react";
import { getHealth } from "../lib/api";
import { formatDateTime } from "../lib/format";
import type { HealthResponse } from "../lib/types";

const CHECK_ORDER = ["bigquery", "firestore", "vertex", "sessions"];

export function HealthStrip() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((h) => {
        if (!cancelled) setHealth(h);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return <p className="health-strip health-strip--error">Health check unavailable.</p>;
  }
  if (!health) {
    return <p className="health-strip muted">Checking health…</p>;
  }

  return (
    <div className="health-strip">
      {CHECK_ORDER.map((name) => {
        const check = health.checks[name];
        if (!check) return null;
        const ok = check.ok === true;
        return (
          <span key={name} className={`health-strip__item ${ok ? "health-strip__item--ok" : "health-strip__item--amber"}`}>
            <span className="health-strip__dot" aria-hidden />
            {name}
            <span className="health-strip__ts">{formatDateTime(check.checked_at)}</span>
          </span>
        );
      })}
    </div>
  );
}

export function TenantLine() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  useEffect(() => {
    let cancelled = false;
    getHealth().then((h) => {
      if (!cancelled) setHealth(h);
    }).catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  if (!health?.tenant) return null;
  const { skus, nodes, customers } = health.tenant;
  const minutesAgo = health.last_sense_run_minutes;
  const ranAt = health.last_sense_run_at ? formatDateTime(health.last_sense_run_at) : undefined;
  return (
    <p className="tenant-line">
      {skus} SKUs, {nodes} nodes, {customers.toLocaleString("en-IN")} customers
      {minutesAgo !== undefined && ranAt ? ` — last Sense run as of ${ranAt} took ${minutesAgo} min` : null}
    </p>
  );
}
