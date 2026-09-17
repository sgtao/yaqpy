"""pyyq - a pure-Python (standard library only) implementation of mikefarah/yq.

>>> import pyyq
>>> pyyq.evaluate(".a.b", "a:\\n  b: 3\\n")
'3\\n'
>>> pyyq.query(".items[] | select(. > 1)", {"items": [1, 2, 3]})
[2, 3]
"""

from pyyq.api import Yq, compile, dump, evaluate, evaluate_all, load, query, update
from pyyq.core.lang.parser import Expression
from pyyq.core.model.node import Kind, Node, Style
from pyyq.errors import (
    EvaluationError, EvaluationLimitError, ExpressionSyntaxError, FormatError, SecurityError,
    UnknownFormatError, YamlSyntaxError, YqError,
)
from pyyq.options import JsonOptions, Limits, Options, PropertiesOptions, SecurityPolicy, YamlOptions

__version__ = "0.1.0"

__all__ = [
    "Yq", "compile", "dump", "evaluate", "evaluate_all", "load", "query", "update",
    "Expression", "Kind", "Node", "Style",
    "EvaluationError", "EvaluationLimitError", "ExpressionSyntaxError", "FormatError",
    "SecurityError", "UnknownFormatError", "YamlSyntaxError", "YqError",
    "JsonOptions", "Limits", "Options", "PropertiesOptions", "SecurityPolicy", "YamlOptions",
    "__version__",
]
