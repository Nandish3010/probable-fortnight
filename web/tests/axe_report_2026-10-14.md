# Axe report, 14 Oct 2026 (final-week B4; supersedes the 12 Oct report, which is kept)

Mock mode, `@axe-core/playwright`, tags wcag2a, wcag2aa, wcag21a, wcag21aa and best-practice (the 12 Oct report left best-practice out, which is why it showed no moderate findings), reduced motion on, page settled 300 ms after load.
Produced by `tests/e2e/axe-report.spec.ts` (`TAAL_AXE_REPORT=1`). Desktop is 1280x800, phone is 390x844.
A cell is the number of violations axe rates serious or critical; the last column counts the moderate and minor ones. First paint of each route only; the open-card, post-Approve and dialog states are in a11y.spec.ts and demo-path.spec.ts.

| Route | Theme | Viewport | Serious + critical | Moderate + minor |
|---|---|---|---|---|
| / | light | desktop | 0 | 0 |
| /desk | light | desktop | 0 | 0 |
| /phone | light | desktop | 0 | 2 |
| /chat | light | desktop | 0 | 1 |
| /outcomes | light | desktop | 0 | 0 |
| / | light | phone | 0 | 1 |
| /desk | light | phone | 0 | 0 |
| /phone | light | phone | 0 | 2 |
| /chat | light | phone | 0 | 1 |
| /outcomes | light | phone | 0 | 0 |
| / | dark | desktop | 0 | 0 |
| /desk | dark | desktop | 0 | 0 |
| /phone | dark | desktop | 0 | 2 |
| /chat | dark | desktop | 0 | 1 |
| /outcomes | dark | desktop | 0 | 0 |
| / | dark | phone | 0 | 1 |
| /desk | dark | phone | 0 | 0 |
| /phone | dark | phone | 0 | 2 |
| /chat | dark | phone | 0 | 1 |
| /outcomes | dark | phone | 0 | 0 |

20 scans; 0 with a serious or critical violation.

## Moderate and minor findings (rule ids)

- /phone, light, desktop: `heading-order` (moderate, 1 node)
- /phone, light, desktop: `image-redundant-alt` (minor, 7 nodes)
- /chat, light, desktop: `heading-order` (moderate, 1 node)
- /, light, phone: `landmark-unique` (moderate, 2 nodes)
- /phone, light, phone: `heading-order` (moderate, 1 node)
- /phone, light, phone: `image-redundant-alt` (minor, 7 nodes)
- /chat, light, phone: `heading-order` (moderate, 1 node)
- /phone, dark, desktop: `heading-order` (moderate, 1 node)
- /phone, dark, desktop: `image-redundant-alt` (minor, 7 nodes)
- /chat, dark, desktop: `heading-order` (moderate, 1 node)
- /, dark, phone: `landmark-unique` (moderate, 2 nodes)
- /phone, dark, phone: `heading-order` (moderate, 1 node)
- /phone, dark, phone: `image-redundant-alt` (minor, 7 nodes)
- /chat, dark, phone: `heading-order` (moderate, 1 node)
