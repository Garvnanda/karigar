"""JobResult: the one shape every order reply takes. Written by code only, never by the LLM.

`Orchestrator.handle` returns `JobResult(...).model_dump()`. The older keys (`status`,
`order_id`, `question`, `explanation`, `results`, `brief`, `plan`) stay so callers keep working.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

Status = Literal["done", "infeasible", "needs_info", "rate_set", "out_of_scope"]


class Achievable(BaseModel):
    value: float
    unit: str


class Infeasible(BaseModel):
    """Why the order can't be made as asked, the closest thing that can, and what to change."""
    binding_constraint: str = Field(min_length=1)
    best_achievable: Achievable
    alternatives: list[str] = Field(min_length=2)


class VariantResult(BaseModel):
    variant: str
    weights: dict[str, float] = {}      # modelled_g, finished_g
    files: dict[str, str] = {}
    quote: dict = {}


class JobResult(BaseModel):
    status: Status
    order_id: str
    lang: str = "en"
    reply: Optional[str] = None          # the counter's text for needs_info / rate_set / out_of_scope
    question: Optional[str] = None       # needs_info: all questions joined into one reply
    questions: list[str] = []
    topics: list[str] = []               # which blocking fields were asked for
    explanation: Optional[str] = None    # infeasible
    infeasible: Optional[Infeasible] = None
    brief: Optional[dict] = None
    plan: Optional[dict] = None
    results: list[VariantResult] = []
    rates: Optional[dict] = None         # rate_set: {"rates": {karat: rate}, "set_at": iso}
    suggestion: Optional[str] = None     # out_of_scope: nearest supported piece

    @model_validator(mode="after")
    def _status_fields(self):
        if self.status == "infeasible" and self.infeasible is None:
            raise ValueError("an infeasible result must carry binding_constraint, best_achievable, alternatives")
        if self.status == "needs_info" and not self.question:
            raise ValueError("a needs_info result must carry a question")
        return self
