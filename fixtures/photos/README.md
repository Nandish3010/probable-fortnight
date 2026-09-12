# Staged pallet photos

Three preloaded pallet photos back the phone view's "use a sample pallet photo" choice. The image
files are not in the repository (`fixtures/photos/originals/` is gitignored); what the stub vision
backend returns for each is in `pallet_0N.json`, recorded from a Vertex run and hand-checked. In
`vertex` mode the same photo refs are sent to Gemini and the JSON files are the accuracy baseline
(`harness/checklists/vision_intake.md`: 30 staged photos, >= 90% date read accuracy at confidence
>= 0.7).

Filming rule (DECISIONS §5.1): dates fill at least a quarter of the frame; two-pass reading (find the
label, then read the crop) when a single pass reports a date confidence below 0.7.
