# Self-hosted fonts

These font files are served from this repository instead of being fetched from
fonts.googleapis.com at build time. They were self-hosted to remove a build-time
dependency on Google Fonts (a failed fetch there broke `next build`).

| File | Family | Subset | Weights |
| --- | --- | --- | --- |
| IBMPlexSans-Variable-latin.woff2 | IBM Plex Sans (variable) | latin | 400, 500, 600 |
| IBMPlexMono-Regular-latin.woff2 | IBM Plex Mono | latin | 400 |
| IBMPlexMono-Medium-latin.woff2 | IBM Plex Mono | latin | 500 |
| NotoSansKannada-Variable-kannada.woff2 | Noto Sans Kannada (variable) | kannada | 400, 500, 600 |

The two variable files each cover all three weights the app uses, so one file
serves 400, 500 and 600.

Copyright:

- IBM Plex Sans and IBM Plex Mono: Copyright IBM Corp.
- Noto Sans Kannada: Copyright Google LLC / The Noto Project Authors.

License: SIL Open Font License 1.1, https://openfontlicense.org/

The fonts are loaded in `web/app/layout.tsx` with `next/font/local`.
