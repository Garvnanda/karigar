# Brag Plan: Karigar

## What is this app?
An AI artisan for a jeweller's shop: a Hinglish request in, five agents work it, and out comes a castable design solved to the exact weight of the customer's old gold, with renders, a casting file, an AR model and a job card.

## The angle
Gold is exact; design never was. Karigar is the first time the design obeys the gold. Treated like a heist-film trailer for a jewellery workshop: velvet-black tray, gold light, five named specialists assembling around one order. The drama is the arithmetic: 18.4 g in, 18.59 g modelled, ±0.3%. Then the twist: it is honest. It refuses what can't be made and asks when it doesn't know.

## Hook (first 2-3 seconds)
Black velvet. One line in big serif caps: "IN EVERY HOME, THERE IS A DRAWER." Then the drawer's contents: a thin gold kangan drawn in light, labelled 18.4 g · 22K.

## Key moments (the middle)
- The Hinglish request typing itself into a chat bubble, verbatim from README.
- Five agents light up one by one across a shop-floor map: Sakhi (Counter), Jauhari (Gold desk), Naqqash (Design studio), Karigar (Workshop), Chitrakar (Photo studio).
- Old kangan melts into a gold orb that flows into the new kada; scale balances exactly.
- Deliverables fan out like cards: three designs, catalog photos, casting file, AR model, job card.
- Refusal: "purani 22K chain 3g se naya kangan banao" → real reply: below the minimum for a bangle that survives daily wear, offers a pendant / 14K / a little more gold.
- Follow-up: "kuch sundar sa bana do" → Sakhi asks "Aap anguthi, choodi ya pendant mein se kya banwana chahenge?"

## Outro / punchline
KARIGAR slams in. "Bring your old gold. Leave with exactly that gold, ready to cast."

## User flow worth showing
Request typed in Hinglish → five agents solve it to the gold → designs and files delivered. Plus two branches: impossible → honest refusal with options; vague → one follow-up question.

## Tone
- Preset: cinematic
- Creative direction: user: "3–4 min explainer … motion graphics only"; trailer-scale jeweller's workshop
- Interpretation: big serif caps, slow confident reveals, long reading holds because it is an explainer; numbers are the spectacle.

## Format: landscape — 1920x1080
## Duration: ~210 s (user override of the 15–25 s default: explicit `--duration 210`, "3–4 min explainer"). Scene lengths flex to the generated narration.

## Visual identity (no frontend in project; derived from subject: jeweller's velvet tray)
- Background: #120D0A (velvet black-brown), local radial glow of #C9973F at ~18%
- Accent: #E0B25A (22K gold)
- Text: #F3E9D6 (ivory)
- Refusal accent: #B23A48 (ruby); follow-up accent: #3E9B74 (emerald)
- Display font: Playfair Display (bundled), caps for hero lines
- Body font: EB Garamond (bundled); numbers/chat/files: IBM Plex Mono (bundled)
- Strongest visual element: the gold equation and the five-zone shop floor

## Share copy (draft)
Bring Nani's old kangan, leave with a new kada made from exactly that gold. Karigar: five AI agents in a jeweller's shop, honest enough to say no.

## Audio direction
- Role: cinematic support under narration
- Music: vol-12 (steady, cinematic per audio.md) for 0–117 s, then vol-9 for the rest, crossfaded
- Music treatment: 0.32 bed, ducked to ~0.13 under narration (narration runs most of the film); fade out under outro
- Music cue guidance: preset `assets/music/cues/happy-beats-business-moves-vol-12-by-ende-dot-app.music-cues.json`, 109.96 BPM; strong cue 8.74 s near the hook's kangan reveal. Rest of the film is narration-led; cue locks optional.
- Audio-reactive treatment: subtle; background gold glow breathes with music RMS. No waveforms.
- SFX posture: sparse; impactSoft_medium on scene reveals, card sounds on the files fan-out, keypress on typed requests, impactBell_heavy on the outro, error-ish soft hit on the refusal.
- Restraint rule: never cover narration with loud hits; SFX ≤ 0.6.

## Storyboard (revised per user: visuals + idea first, minimal tech/pricing; durations = narration + ~1.5 s)

1. Drawer (hook) — velvet black, "IN EVERY HOME, THERE IS A DRAWER." Gold kangan + chain drawn in light.
2. The guess — balance scale tipping; chips "+ add gold?" "− take some back?"; title "GOLD IS EXACT. DESIGN NEVER WAS."
3. Reveal — KARIGAR wordmark, "An AI artisan for anything that gets made."
4. The request — Hinglish sentence types into a chat bubble (keypress SFX).
5. Five agents — shop-floor plan; Sakhi, Jauhari, Naqqash, Karigar, Chitrakar light up one by one with zone + job.
6. The magic — kangan melts to a glowing gold orb, which flows into a new beaded kada; a scale balances perfectly: "THE DESIGN BENDS TO THE GOLD."
7. What comes out — three design cards (kada, solitaire ring, lotus pendant), then deliverable chips: catalog renders · casting file · AR model · job card.
8. It says no — "purani 22K chain 3g se naya kangan banao" → ruby reply: too little gold for a bangle that survives daily wear; options: a pendant · 14K gold · add a little gold.
9. It asks — "kuch sundar sa bana do" → emerald Sakhi bubble "Aap anguthi, choodi ya pendant mein se kya banwana chahenge?"
10. Why it matters — three columns: Jeweller / Customer / Workshop.
11. What's next — Nonilion rooms · AR try-on · "make it 2 g lighter" · learns each workshop · hardware pack.
12. Outro — KARIGAR + "Bring your old gold. Leave with exactly that gold, ready to cast."

## Voiceover script (Kokoro, voice af_heart)
1. In every Indian home, there is a drawer. And in that drawer, old gold. A grandmother's kangan. A chain from a wedding, long ago. Gold that carries a story, waiting to become something new.
2. But turning old gold into a new piece has always been guesswork. The new design weighs whatever it weighs. Then comes the back and forth. Add more gold, or take some back. Gold is exact. Design never was.
3. Until now. Meet Karigar. An AI artisan that turns a simple request into a new piece, made from exactly your gold, and ready to cast.
4. It starts the way every order starts. A customer, speaking the way people really speak. In Hinglish. No forms. No menus. Just a sentence.
5. Then five agents go to work across the shop floor. Sakhi, at the counter, listens, and asks when something is missing. Jauhari, the gold expert, works out exactly how much gold the new piece will carry. Naqqash, in the design studio, sketches three designs. Karigar, in the workshop, shapes each one, and makes sure it can really be cast. And Chitrakar, in the photo studio, makes it beautiful.
6. And here is the magic. The design bends to fit the gold, not the other way around. Karigar reshapes every design until it carries exactly the gold you brought in. A grandmother's kangan becomes a new kada. Gram for gram.
7. In minutes, the shop has everything. Three designs to choose from. Catalog photos. A file, ready for casting. A model to see in AR. And a job card for the workshop.
8. And when a request simply can't be made, Karigar says so. Three grams of old chain, for a whole new kangan? It won't fake a yes. It explains why, and offers the closest real options. A pendant, perhaps. Or a little more gold.
9. And when a request is too vague, it doesn't guess. It asks. In the customer's own language. Just like a good shopkeeper would.
10. For the jeweller, no more guesswork, and no awkward haggling over grams. For the customer, a family heirloom, reborn, and seen before a single gram is melted. For the workshop, a design that can actually be made.
11. And this is only the beginning. Karigar moves into Nonilion rooms, where every agent has a seat on the shop floor. Try the piece on in AR, straight from the chat. Say, make it two grams lighter, and it reshapes in seconds. Every workshop teaches it a little more, with every casting. And the same engine reaches beyond gold, into hardware.
12. Karigar. Bring your old gold. Leave with exactly that gold, ready to cast.

## Grounding notes
- User direction (mid-run): hackathon pitch of what was built; NO pricing anywhere; keep technical detail out; focus on visuals and why the idea is good, different and useful.
- Capabilities shown are from README: five agents and roles, Hinglish, solve to old-gold weight, castability check, 3 variants, renders, STL, GLB for AR, job card, refusal with options, follow-up question. Refusal and follow-up lines are real outputs of the code.
- Roadmap items shown as "next", not shipped.

**Music mood:** cinematic. **Audio summary:** steady cinematic bed ducked under a calm narrator, sparse weighted hits on reveals, a bell to close.
