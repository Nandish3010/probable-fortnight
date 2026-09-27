# Staged pallet photos

Seven preloaded pallet photos back the phone view's "use a sample pallet photo" choice (an eighth,
`pallet_07.jpg`, is committed but not wired into the picker -- see below). `pallet_01`-`03.jpg` are
real staged photos, hand-checked; their `pallet_0N.json` rows are recorded from a Vertex run. In
`vertex` mode the same photo refs are sent to Gemini and the JSON files are the accuracy baseline
(`harness/checklists/vision_intake.md`: 30 staged photos, >= 90% date read accuracy at confidence
>= 0.7).

`pallet_04`-`08.jpg` are AI-generated (not real photographs), added for demo variety, at a lower
resolution (200x200, vs. 1024x1024 for the real photos) due to an environment constraint on the
image-generation tool used. Their `.json` rows are written to match real catalogue SKUs where the
pictured products exist there (rice, dal, oil, atta, poha, milk, paneer), all marked
`needs_confirmation: true` with a lower confidence, since the exact printed dates were not
independently verified against the (low-resolution) image the way the first three were.
`pallet_07.jpg` depicts "namkeen" and "wafers", neither of which exist as catalogue SKUs, so it
was deliberately left out of the phone view's picker rather than given a fabricated SKU match; it
remains available as a plain image asset if needed elsewhere (e.g. a deck or screenshot).

Filming rule (DECISIONS §5.1): dates fill at least a quarter of the frame; two-pass reading (find the
label, then read the crop) when a single pass reports a date confidence below 0.7.
