# Notice

Cube Labeler
Copyright (C) 2026 McTobe

This program is free software: you can redistribute it and/or modify it under the terms of
the GNU Affero General Public License as published by the Free Software Foundation, version 3
of the License (see [LICENSE](LICENSE)).

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
the GNU Affero General Public License for more details.

If you run a modified version of Cube Labeler where other people can use it over a network
(for example a hosted web app), the license asks you to offer them the source code of your
version too.

## Exception: code based on Ircama/PT-P300BT

The following files are based on code from https://github.com/Ircama/PT-P300BT and are **not**
covered by the license above:

- `core/ptcbp.py`
- `core/ptstatus.py`

Ircama/PT-P300BT does not state a license, so these files remain subject to the rights of
their original author. They are credited and included here for compatibility with that
project until its author adds a license.

## Third-party parts

- Fonts in `web/fonts/`, all under the SIL Open Font License 1.1: Arimo (`OFL.txt`), and Atkinson
  Hyperlegible, Barlow Condensed, Bebas Neue, Caveat, Cinzel, Comic Neue, EB Garamond, Fredoka, Great
  Vibes, Inter, JetBrains Mono, Lexend, Montserrat, Nunito, Open Sans, Oswald, Pacifico, Patrick Hand,
  Roboto and Zilla Slab (each with its own `OFL-<name>.txt`). The static Arimo Medium and SemiBold,
  Caveat, Cinzel, EB Garamond, Fredoka, Inter, JetBrains Mono, Lexend, Montserrat, Nunito, Open Sans,
  Oswald and Roboto files are made from the upstream variable fonts, and all but Arimo Regular and Bold
  are cut down to Latin characters. None of these use a Reserved Font Name (Lexend reserves only
  "RevReading Lexend"); fonts that reserve their name, such as Playfair Display, are left out.
- Preact and htm (`web/vendor/`), under the MIT License (see `web/vendor/README.md`).
