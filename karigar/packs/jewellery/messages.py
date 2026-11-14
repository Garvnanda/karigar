"""Every user-facing sentence Sakhi writes in Phase 1, in English and Hinglish.

Numbers are formatted by code before they reach a template; templates never compute.
"""
from __future__ import annotations

from karigar.core.lang import EN, HINGLISH

T: dict[str, dict[str, str]] = {
    # --- questions (blocking fields only) ---
    "q_piece": {
        EN: "What would you like made: a ring, bangle, pendant, chain, coin, earrings or a nose pin?",
        HINGLISH: "Kya banana hai: ring, bangle, pendant, chain, sikka, earrings ya nose pin?",
    },
    "q_target": {
        EN: "How should I size it? Tell me your old gold's weight and karat, a target weight, or a budget.",
        HINGLISH: "Kitna sona lagana hai? Purane sone ka weight aur karat, target weight, ya budget batayein.",
    },
    "q_reference": {
        EN: "Please send a photo of the piece, or tell me its current weight (g) and size, "
            "so I can rebuild it lighter.",
        HINGLISH: "Piece ki photo bhejiye, ya uska abhi ka weight (g) aur size batayein, "
                  "taaki main use halka bana sakun.",
    },
    "q_ring_size": {
        EN: "What is the ring size? An Indian size number (1-30) or the inner diameter in mm.",
        HINGLISH: "Ring ka size kya hai? Indian size number (1-30) ya andar ka diameter mm mein batayein.",
    },
    "q_bangle_size": {
        EN: "What is the bangle size? An Indian size like 2-4, 2-6 or 2-8, or the inner diameter in mm.",
        HINGLISH: "Bangle ka size kya hai? 2-4, 2-6, 2-8 jaisa Indian size, ya andar ka diameter mm mein.",
    },
    "q_chain_length": {
        EN: "What chain length: 16, 18, 20, 22 or 24 inches?",
        HINGLISH: "Chain kitni lambi chahiye: 16, 18, 20, 22 ya 24 inch?",
    },
    "q_karat": {
        EN: "Which purity for the new piece: 22K, 18K or 14K?",
        HINGLISH: "Naya piece kitne karat ka chahiye: 22K, 18K ya 14K?",
    },
    "q_old_karat": {
        EN: "What karat is the old gold: 24K, 22K, 18K or 14K?",
        HINGLISH: "Purana sona kitne karat ka hai: 24K, 22K, 18K ya 14K?",
    },
    "q_unreadable": {
        EN: "I couldn't read the {field} correctly. Could you say it again?",
        HINGLISH: "{field} theek se samajh nahi aaya. Ek baar phir batayein?",
    },
    "q_intro": {
        EN: "A few details before I start: {items}",
        HINGLISH: "Shuru karne se pehle kuch baatein: {items}",
    },
    # --- scope ---
    "out_of_scope": {
        EN: "Right now I design rings, bangles, pendants, chains, coins, earrings and nose pins only, "
            "so I can't make {asked} yet. "
            "The nearest I can do is a {nearest}. Shall I make a {nearest} instead?",
        HINGLISH: "Abhi main sirf ring, bangle, pendant, chain, sikka, earrings aur nose pin banati hoon; "
                  "{asked} abhi nahi bana sakti. "
                  "Sabse kareeb {nearest} hai. Kya {nearest} bana doon?",
    },
    # --- gold rate ---
    "rate_set": {
        EN: "Gold rate saved: {rates} (set {when}). I'll use it for quotes.",
        HINGLISH: "Rate save kar liya: {rates} ({when} par set). Quote isi se banega.",
    },
    "rate_not_allowed": {
        EN: "Only the shop owner or staff can set the gold rate, so I haven't changed it; "
            "quotes use the shop's configured gold rate. Is there a piece you'd like made?",
        HINGLISH: "Gold rate sirf dukaan ke owner ya staff set kar sakte hain, isliye maine rate nahi badla; "
                  "quote dukaan ke configured gold rate se banega. Koi piece banwana hai?",
    },
    # Rate missing / stale / out of range: say so, ask for today's rate, never estimate.
    "rate_missing": {
        EN: "I don't have a {karat}K gold rate on file, and I never estimate it. "
            "What is today's {karat}K rate? Please ask the shop owner to update it "
            "(rate job or config), then send the order again.",
        HINGLISH: "Mere paas {karat}K ka gold rate nahi hai, aur main rate kabhi andaaze se nahi lagati. "
                  "Aaj ka {karat}K rate kya hai? Dukaan ke owner se rate update karwaiye "
                  "(rate job ya config), phir order dobara bhejiye.",
    },
    "rate_stale": {
        EN: "The {karat}K gold rate on file ({rate}/g, set {when}) is more than {hours} h old, "
            "and I never estimate it. What is today's {karat}K rate? Please ask the shop owner to "
            "update it, then send the order again.",
        HINGLISH: "File mein {karat}K ka rate ({rate}/g, {when} par set) {hours} ghante se purana hai, "
                  "aur main rate andaaze se nahi lagati. Aaj ka {karat}K rate kya hai? Owner se rate "
                  "update karwaiye, phir order dobara bhejiye.",
    },
    "rate_out_of_range": {
        EN: "The {karat}K gold rate on file ({rate}/g, set {when}) is outside the sane range "
            "({lo}–{hi}/g), so I won't use it, and I never estimate one. What is today's {karat}K rate? "
            "Please ask the shop owner to correct it, then send the order again.",
        HINGLISH: "File mein {karat}K ka rate ({rate}/g, {when} par set) sahi range ({lo}–{hi}/g) se "
                  "bahar hai, isliye main ise use nahi karungi aur andaaza bhi nahi lagaungi. Aaj ka "
                  "{karat}K rate kya hai? Owner se rate theek karwaiye, phir order dobara bhejiye.",
    },
    "rate_future": {
        EN: "The {karat}K gold rate on file ({rate}/g) is stamped in the future ({when}), so I won't use it, "
            "and I never estimate one. What is today's {karat}K rate? Please ask the shop owner to "
            "update it, then send the order again.",
        HINGLISH: "File mein {karat}K ka rate ({rate}/g) aage ki tareekh ({when}) ka hai, isliye main ise "
                  "use nahi karungi aur andaaza bhi nahi lagaungi. Aaj ka {karat}K rate kya hai? Owner se "
                  "rate update karwaiye, phir order dobara bhejiye.",
    },
    "rate_invalid": {
        EN: "That rate doesn't look right ({bad}). Please send it again, e.g. \"rate 22K 14730\".",
        HINGLISH: "Ye rate sahi nahi lag raha ({bad}). Phir se bhejiye, jaise \"aaj ka rate 22K 14730\".",
    },
    # --- brief summary ---
    "got_it": {EN: "Got it.", HINGLISH: "Samajh gayi."},
    "summary": {
        EN: "{article} {karat}K {metal} gold {piece} from {src}{gem}{style}.",
        HINGLISH: "{karat}K {metal} gold ki {piece}, {src}{gem}{style}.",
    },
    "src_old": {EN: "{w} g old {k}K gold", HINGLISH: "{w} g purane {k}K sone se"},
    "src_weight": {EN: "{w} g", HINGLISH: "{w} g ki"},
    "src_budget": {EN: "a budget of {b}", HINGLISH: "{b} ke budget mein"},
    "default_metal": {
        EN: "Metal colour: yellow gold (default; say rose or white to change).",
        HINGLISH: "Metal colour: yellow gold (default; rose ya white chahiye to batayein).",
    },
    "default_stone": {
        EN: "Stone size: {ct} ct (default for a {piece}; tell me yours to change).",
        HINGLISH: "Stone size: {ct} ct ({piece} ka default; alag chahiye to batayein).",
    },
}

def t(key: str, lang: str, **kw) -> str:
    table = T[key]
    return table.get(lang, table[EN]).format(**kw)


def join_questions(questions: list[str], lang: str) -> str:
    """One reply that carries up to three questions."""
    if len(questions) == 1:
        return questions[0]
    items = " ".join(f"({i}) {q}" for i, q in enumerate(questions, 1))
    return t("q_intro", lang, items=items)
