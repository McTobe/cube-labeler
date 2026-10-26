# Cube Labeler design guide

How the app should look and feel, mainly the web version (2.0 and later). Use it when building
or reworking a page. The icon editor, the Settings page and the bin label editor are the
reference designs.

## Principles

1. **Polished first.** A clean, uniform and professional look matters more than filling every
   pixel.
2. **Bento grid on wide screens.** Boxes fit together into a neat rectangle and columns end on
   the same line. Nothing is left ragged.
3. **One standard size per control.** Fields, pills and buttons look the same everywhere.
   Nothing stretches to fill space. If there is room left over, the box shrinks to fit its
   content instead.
4. **Editors in columns.** An editor splits into columns with thin dividers that read left to
   right, like the icon editor (picture, conversion, preview) and the bin label editor (size
   and name, bins and lengths, drive).
5. **Even grids, no orphans.** Pills and picture tiles sit in tidy rows, with no single item left
   alone on a row.
6. **No layout shifts.** The label preview keeps its size when switching modes, and status
   messages float over it instead of pushing things down.
7. **Work in the middle, settings on the right.** The main work area sits under the preview. The
   side panel holds the mode picker, settings and a short how-to, and it may end partly empty.
8. **Quiet extras.** Secondary information goes in slim, muted lines instead of boxes of its
   own, like the About line at the bottom of Settings.
9. **Phones get one column.** On a narrow screen the same parts stack in the same order, and
   extras such as the how-to box are left out.
10. **Built to grow.** Lists of choices are data, so new kinds of labels (for example network
    port tags) are added to the mode picker without a redesign.

## Checking a change

Look at a page in a 1920 px wide window, a smaller desktop window (around 1440 px) and a phone,
in both light and dark themes, before calling it done.
