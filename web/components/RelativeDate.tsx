import { formatDate, relativeDate } from "../lib/format";

/** A deadline as "in 6 days" / "6 days ago" with the full date in the tooltip. Relative to the
 * demo clock the server reports (`now`); until that has loaded it shows the plain date instead of
 * a countdown against the browser's own clock. `long` adds the short date in brackets
 * ("in 6 days (Fri 18 Sep)") for places where a hover is not enough, such as a phone. */
export function RelativeDate({ date, now, long = false }: { date: string | null | undefined; now?: Date; long?: boolean }) {
  if (!date) return <>–</>;
  const rel = now ? relativeDate(date, now) : null;
  if (!rel) return <>{formatDate(date)}</>;
  return (
    <time dateTime={date.slice(0, 10)} title={rel.absolute}>
      {long ? rel.long : rel.text}
    </time>
  );
}
