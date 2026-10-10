"use client";

import { useEffect, useState } from "react";
import { getHealth } from "../lib/api";
import { count, dayMonth, formatDateTime, formatDuration } from "../lib/format";
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
  const minutes = health.last_sense_run_minutes;
  const rawAt = health.last_sense_run_at;
  // A bare date ("2026-09-12") is shown as "12 Sep"; a full timestamp keeps its time.
  const ranAt = rawAt ? (/^\d{4}-\d{2}-\d{2}$/.test(rawAt) ? dayMonth(rawAt) : formatDateTime(rawAt)) : undefined;
  return (
    <p className="tenant-line">
      {skus} SKUs, {nodes} nodes, {count(customers)} customers
      {minutes !== undefined && ranAt ? ` — last stock scan as of ${ranAt} took ${formatDuration(minutes * 60)}` : null}
    </p>
  );
}
