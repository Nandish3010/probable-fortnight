Build: `make setup` once, then `make deck` renders `deck/slides.html` to `docs/deck.pdf` (17 pages) and `deck/png/slide_NN.png` (1920x1080, for the video).
Every number on a slide must trace to a file in the repo; see `deck/claims.md` (checked by `make docs`). Screenshots in `deck/img/` are crops of real captures of the running app.
The QR codes on slide 17 are inline SVG made with the Python `qrcode` package (error correction M) for the two URLs printed under them.
