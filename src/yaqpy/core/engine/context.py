"""Context (the current matching nodes + variables) and EvalEnv (design doc 7-1)."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from yaqpy.core.engine.limits import StepBudget
from yaqpy.core.model.node import Node
from yaqpy.options import Limits, Options, SecurityPolicy


@dataclass(frozen=True, slots=True)
class Context:
    """Go's ``Context``. Immutable: every change returns a new Context."""

    nodes: tuple[Node, ...] = ()
    variables: Mapping[str, tuple[Node, ...]] = field(default_factory=dict)
    read_only: bool = False
    datetime_layout: str | None = None

    def child(self, nodes: Iterable[Node]) -> Context:
        return Context(tuple(nodes), self.variables, self.read_only, self.datetime_layout)

    def single_child(self, node: Node) -> Context:
        return Context((node,), self.variables, self.read_only, self.datetime_layout)

    def single_readonly_child(self, node: Node) -> Context:
        return Context((node,), self.variables, True, self.datetime_layout)

    def clone(self) -> Context:
        return self.child(self.nodes)

    def readonly_clone(self) -> Context:
        return Context(self.nodes, self.variables, True, self.datetime_layout)

    def writable_clone(self) -> Context:
        return Context(self.nodes, self.variables, False, self.datetime_layout)

    def deep_clone(self) -> Context:
        return self.child(n.copy() for n in self.nodes)

    def with_variable(self, name: str, value: tuple[Node, ...]) -> Context:
        variables = dict(self.variables)
        variables[name] = value
        return Context(self.nodes, variables, self.read_only, self.datetime_layout)

    def get_variable(self, name: str) -> tuple[Node, ...] | None:
        return self.variables.get(name)

    def get_datetime_layout(self) -> str:
        return self.datetime_layout or "2006-01-02T15:04:05Z07:00"

    def __len__(self) -> int:
        return len(self.nodes)

    def evaluate_all_together(self) -> bool:
        return all(n.evaluate_together for n in self.nodes)


def system_clock() -> datetime:
    """The current time in the local zone (Go's ``time.Now``)."""
    return datetime.now().astimezone()


@dataclass(frozen=True, slots=True)
class EvalEnv:
    """Everything one evaluation needs from the outside world."""

    operators: Any                      # OperatorRegistry
    security: SecurityPolicy = field(default_factory=SecurityPolicy.strict)
    environ: Mapping[str, str] = field(default_factory=dict)
    file_loader: Callable[[str], str] | None = None
    limits: Limits = field(default_factory=Limits)
    budget: StepBudget = field(default_factory=StepBudget)
    options: Options = field(default_factory=Options)
    formats: Any = None                 # FormatRegistry (injected by app layer)
    yaml_snippet_decoder: Callable[[str], Node] | None = None
    clock: Callable[[], datetime] = system_clock       # ``now`` and ``shuffle`` read this
