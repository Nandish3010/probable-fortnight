-- Assertion: no play with an online channel/mechanic targets a gap whose online sell-by
-- deadline has already passed as of the gap's own creation date (a lot past its sell-by must
-- move through outlet_markdown or transfer_plus_nudge, never an online mechanic).
-- Zero rows returned = pass.
SELECT pl.tenant_id, pl.play_id, pl.gap_id, pl.channel, pl.mechanic, g.deadline_date, g.created_at
FROM plays pl
JOIN gaps g
  ON g.tenant_id = pl.tenant_id AND g.gap_id = pl.gap_id
WHERE pl.channel <> 'outlet'
  AND pl.mechanic NOT IN ('outlet_markdown', 'transfer_plus_nudge')
  AND g.deadline_type = 'online_sellby'
  AND g.deadline_date < g.created_at;
