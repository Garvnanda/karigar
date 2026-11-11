"""Where agent output goes.

The engine never talks to a chat platform directly. It calls a Transport,
so the same pipeline runs in the terminal today and in Nonilion once its
Bot API is wired in.
"""
from __future__ import annotations

from pathlib import Path


class Transport:
    """Interface. Every method is fire-and-forget from the engine's point of view."""

    def say(self, agent: str, text: str) -> None:
        raise NotImplementedError

    def progress(self, agent: str, text: str) -> None:
        self.say(agent, text)

    def send_file(self, agent: str, path: Path, caption: str = "") -> None:
        raise NotImplementedError

    def send_image(self, agent: str, path: Path, caption: str = "") -> None:
        self.send_file(agent, path, caption)

    def move_to(self, agent: str, zone: str) -> None:
        """Office action: walk to a zone (counter, studio, workshop, pricing, photo)."""

    def ask(self, agent: str, question: str) -> None:
        self.say(agent, question)


class ConsoleTransport(Transport):
    def say(self, agent, text):
        print(f"[{agent}] {text}", flush=True)

    def progress(self, agent, text):
        print(f"  … {agent}: {text}", flush=True)

    def send_file(self, agent, path, caption=""):
        print(f"[{agent}] 📎 {Path(path).name}  {caption}", flush=True)

    def move_to(self, agent, zone):
        print(f"  ↪ {agent} walks to the {zone}", flush=True)


class NonilionTransport(Transport):
    """Placeholder: fill in once Nonilion shares the Bot API developer guide.

    Expected mapping (to confirm against the guide):
      say          -> post a chat message as this agent's bot identity
      progress     -> post a progress update in the room
      send_file    -> upload/attach a file (or post a public link hosted on Render)
      send_image   -> post an image inline
      move_to      -> office action: walk to a zone/person
      ask          -> post a follow-up question and wait for the reply
    One bot token per agent (Sakhi, Naqqash, Karigar, Jauhari, Chitrakar).
    """

    def __init__(self, tokens: dict[str, str]):
        self.tokens = tokens

    def say(self, agent, text):  # pragma: no cover - needs the real API
        raise NotImplementedError("Wire to Nonilion Bot API (see class docstring)")
