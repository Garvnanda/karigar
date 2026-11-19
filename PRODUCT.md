# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Indian jewellery shop owners (and their staff) who take custom orders: a customer asks in Hinglish for a piece, often trading in old gold, and the jeweller needs a castable design, its gold weight and a quote they can defend at the counter. The web console is, for now, used **mostly as a demo** to judges and investors (user, 2026-11-14), so it must also read well to someone seeing it for the first time.

## Product Purpose
Karigar turns a jeweller's Hinglish request into a castable design solved to a gold weight or budget, with renders, STL, job card and quote. The console shows each order end to end: what was understood, the designs, the quote with its sources, the weight, mesh checks, files and edits.

## Positioning
Every number shown (weight, price, rate, dimension) comes from code and data, never from the LLM. The design is solved to the stated gold weight or budget and checked on the actual mesh before it is offered.

## Operating Context
- Orders arrive through chat (Sakhi in Nonilion) and are made by a Blender worker on a laptop; the service runs on Render.
- Gold rate: MCX + ₹5,000/10 g, refreshed by a rate job and shown with its timestamp. Quotes use making 3.5%, GST 3% on gold + stones, 5% on making, BIS hallmark ₹75/article, and old-gold credit = weight × purity × 24K rate × 0.98.
- 19 catalogue families: rings, pendants, chains, coin, bangles, earrings, nose pins.

## Capabilities and Constraints
- The demo must run offline. Every LLM path has a deterministic fallback.
- Values that are assumptions (making %, GST treatment, stone rate) are marked "assumed" wherever they appear.
- Planned 3D viewer: the worker exports GLB from Blender (Phase 10).

## Brand Commitments
- Colours: the pitch deck (ppt.pdf): wine #1D0A10 ground, antique gold, warm cream text (user, 2026-11-14; supersedes the earlier off-white pin).
- Feel: showroom luxury (user, 2026-11-14).

## Evidence on Hand
- Real renders and weights come from the Blender geometry (`karigar/packs/jewellery/families/`).
- No real customers, orders or shop names exist yet: all console content is sample data and is labelled as such.

## Product Principles
1. The numbers can be trusted: each shows its source, and assumptions are visible.
2. The piece is the hero: show the actual design, not a placeholder.
3. Hinglish-first: the customer's own words stay visible next to what Karigar understood.
4. Works offline for the demo.
