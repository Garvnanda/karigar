# Karigar design system

Two surfaces share one world, taken from the team's pitch deck (`ppt.pdf`) and video (`Karigar_pitch_v2.mp4`) at the user's request:
- the **customer studio** (`studio/`, served at `/studio/`);
- the **owner workshop console** (`console/`, at `/console/`).

The tokens are in `studio/tokens.css` and re-declared at the top of `studio/studio.css` and `console/console.css`. Each of those two stylesheets starts with its Hallmark stamp and waivers.

## Idea
Every screen is a jeweller's tray. The piece sits lit on wine velvet inside the deck's mandala, and the customer's choices are written on the slip beside it. The tray shows the real design: Blender renders and GLB models from `studio/assets/`, made by `scripts/make_catalogue.py --pictures`. All renders, including order photos, use a wine backdrop (`render._sweep`). The 3D piece re-tints live when the metal colour changes.

## Colour (from the deck)
| Token | Value | Role |
|---|---|---|
| `--color-paper` / `-2` / `-3` | oklch(16.5 / 21 / 26% · wine) ≈ #1D0A10 → #33121B | ground, raised surfaces, tiles |
| `--color-stage` / `-2` | oklch(13 / 24% · wine) | the tray: darker, with a soft lit centre |
| `--color-ink` / `-2` | oklch(93 / 84% · warm cream) | text |
| `--color-muted` | oklch(70% · warm) | secondary text (≥ 4.5:1 on the ground) |
| `--color-accent` | oklch(76% 0.11 78), antique gold | the one filled action, the selected border, prices, small labels |
| `--color-ornament` | oklch(62% 0.09 70) | mandala, arches, the header band, pill and button borders |
| `--color-rule` | oklch(36% · brown) | hairlines |

Selected choices take a gold border on a gold-tinted wine, like the deck's pills. Gold display type appears once per screen, on the price.

## Type
- **Cormorant Garamond** (display, 500/600, plus italic for the lead line): the deck's face, kept at the user's request.
- **Rubik** (body, 400/500): tabular figures for every weight and price.
- **Tiro Devanagari Hindi** (outlier, one role): the कारीगर mark on the intro.
- Labels are sentence case and untracked. Where the deck uses tracked capitals, the UI uses small gold sentence-case labels instead (Hallmark floor).

## Ornament (geometry, never pictures)
- **Mandala:** concentric rings, 16/16/32/48 petal curves and 64 beads, computed in `studio.js`, drawn at 32% opacity behind the piece.
- **Header band:** two hairlines, the deck's top border.
- **Jharokha arches:** a row of arches above the footer, as at the foot of the deck's slides.
- **Pills:** "3 designs, Castable STL, Job card, Quote with old-gold credit", as in the deck.

## Components
- **Choice:** a radio label in one of three layouts: tiles (with a render), chips or rows (with swatches). Every choice has a focus-visible ring.
- **Button:** an outline pill in ornament gold. `btn--gold` is the single filled primary on each screen.
- **Tray:** a `<model-viewer>` with auto-rotate and drag, or a still render, plus a caption.
- **Ledger (console):** a row per placed order with its render, customer, amount due, weights and the cast-weight entry.

## Motion
One moment only: the piece settles onto the tray (420 ms, expo-out). A spinner marks the running stage. Both are off under `prefers-reduced-motion`.

## Rules
- Every number comes from `/shop` or `/api`, which is worker output.
- The customer types only grams, and at checkout a name and phone.
- Checkout is labelled demo and has no card fields.
