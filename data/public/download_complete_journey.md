# Dunnhumby "The Complete Journey": manual download, never automated

The Complete Journey (real household transactions, coupon campaigns and redemptions) is the
preferred public grounding for basket affinity, segment features and coupon-response priors
(DECISIONS §3.1). Its licence requires permission for public use, so:

1. Request permission from dunnhumby (Source Files page) and record the reply in `DATA_LICENSES.md`.
2. Download `dunnhumby_The-Complete-Journey.zip` yourself and unzip it into `data/public/raw/`
   (gitignored). The nine "Let's Get Sort-of-Real" archives are synthetic dummy data and are not used.
3. Run `python -m data.public.transform_complete_journey`. It reads only from `data/public/raw/` and
   writes derived aggregates (affinity scores, segment features, coupon-response priors) into the
   local store. It exits without doing anything when the raw folder is missing, so CI never touches
   the licensed files.

Until permission is granted (decision by 19 Sept), the tenant is fully synthetic and disclosed as
such; the estimator priors are the weak defaults in `data/generator/generate.py::priors`.
