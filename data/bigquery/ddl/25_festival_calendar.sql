-- Festival calendar: source for is_festival regressor windows (DECISIONS §3.2, §5.2).
-- Each row is one named festival window; window_days is the number of days the effect is
-- applied around `date` (see 01_regressors.sql for how the window is expanded).
CREATE TABLE IF NOT EXISTS `taal.festival_calendar` (
  tenant_id STRING NOT NULL,
  name STRING NOT NULL,
  date DATE NOT NULL,
  window_days INT64,
  categories ARRAY<STRING>
)
CLUSTER BY tenant_id, date;
