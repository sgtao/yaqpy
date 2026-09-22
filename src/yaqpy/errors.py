"""Exception hierarchy for yaqpy (design doc section 10-4)."""

from __future__ import annotations

from typing import Any


class YqError(Exception):
    """Base class for every error raised by yaqpy."""

    code = "error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message}

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


class ExpressionSyntaxError(YqError):
    """The expression could not be tokenised or parsed."""

    code = "expression_syntax"

    def __init__(self, message: str, *, expression: str = "", position: int = -1) -> None:
        super().__init__(message)
        self.expression = expression
        self.position = position

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["expression"] = self.expression
        d["position"] = self.position
        return d


class EvaluationError(YqError):
    """An operator failed while evaluating."""

    code = "evaluation"

    def __init__(self, message: str, *, operator: str = "", path: list[Any] | None = None) -> None:
        super().__init__(message)
        self.operator = operator
        self.path = path or []

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        if self.operator:
            d["operator"] = self.operator
        if self.path:
            d["path"] = list(self.path)
        return d


class EvaluationLimitError(EvaluationError):
    """A resource limit (steps, time, depth, alias expansion) was exceeded."""

    code = "evaluation_limit"

    def __init__(self, message: str, *, limit: str = "") -> None:
        super().__init__(message)
        self.limit = limit

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["limit"] = self.limit
        return d


class FormatError(YqError):
    """A document could not be decoded or encoded."""

    code = "format"

    def __init__(
        self,
        message: str,
        *,
        format: str = "",
        filename: str = "",
        line: int = 0,
        column: int = 0,
    ) -> None:
        super().__init__(message)
        self.format = format
        self.filename = filename
        self.line = line
        self.column = column

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["format"] = self.format
        if self.filename:
            d["filename"] = self.filename
        if self.line:
            d["line"] = self.line
            d["column"] = self.column
        return d


class YamlSyntaxError(FormatError):
    """The YAML text is malformed."""

    code = "yaml_syntax"

    def __init__(self, message: str, *, line: int = 0, column: int = 0, filename: str = "") -> None:
        super().__init__(message, format="yaml", filename=filename, line=line, column=column)

    def __str__(self) -> str:
        if self.line:
            return f"line {self.line}: {self.message}"
        return self.message


class UnknownFormatError(FormatError):
    """The requested format name is not registered."""

    code = "unknown_format"


class RecipeError(YqError):
    """A recipe could not be found, read or understood (a yaqpy extension)."""

    code = "recipe"


class SecurityError(YqError):
    """An operator needs a capability the SecurityPolicy does not allow."""

    code = "security"

    def __init__(self, message: str, *, capability: str = "") -> None:
        super().__init__(message)
        self.capability = capability

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["capability"] = self.capability
        return d
