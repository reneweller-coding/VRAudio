# VRAudio

The page of five generative instruments: **[reneweller-coding.github.io/VRAudio](https://reneweller-coding.github.io/VRAudio/)**.

| | genre | |
|---|---|---|
| [Noctuary](https://github.com/reneweller-coding/Noctuary) | ambient and drone | a synthesizer for slowly breathing clusters, a conductor that plays all night |
| [Ephemeris](https://github.com/reneweller-coding/Ephemeris) | Berlin School | sequenced modular voices and a composer of whole pieces and night sets |
| [Phosphene](https://github.com/reneweller-coding/Phosphene) | psytrance | complete sets from a seed: Goa, Full-On, Progressive, Dark Forest, Hi-Tech |
| [Totality](https://github.com/reneweller-coding/Totality) | hypnotic techno | tracks of 32-bar plateaus and DJ sets that mix themselves |
| [Parhelion](https://github.com/reneweller-coding/Parhelion) | trance | the supersaw, a physical piano, a synthesised orchestra |

Each composes its music from a seed and synthesises it while it plays: VST3 and standalone for Windows, Linux and macOS
(Apple Silicon, untested), a Meta Quest app, MIDI out, a stereo output per stem, Ableton Link. Free software under the
AGPL-3.0; every repository has its manual, its releases and a release "demos".

`python make_page.py` writes `index.html` from `page.html` and its table, with the logos and the demo posters taken
from the five repositories beside this one (`Tools/demo/make_demos.py` in each makes the demos). The videos and the
MP3s stay on each repository's release "demos" and are played from there.
