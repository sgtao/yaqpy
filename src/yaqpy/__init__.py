"""yaqpy - a pure-Python (standard library only) implementation of mikefarah/yq.

>>> import yaqpy
>>> yaqpy.evaluate(".a.b", "a:\\n  b: 3\\n")
'3\\n'
>>> yaqpy.query(".items[] | select(. > 1)", {"items": [1, 2, 3]})
[2, 3]
"""

from yaqpy.api import Yq, compile, dump, evaluate, evaluate_all, load, query, update
from yaqpy.core.lang.parser import Expression
from yaqpy.core.model.node import Kind, Node, Style
from yaqpy.errors import (
    EvaluationError, EvaluationLimitError, ExpressionSyntaxError, FormatError, SecurityError,
    UnknownFormatError, YamlSyntaxError, YqError,
)
from yaqpy.options import (
    CsvOptions, JsonOptions, Limits, Options, PropertiesOptions, SchemaOptions, SecurityPolicy,
    TomlOptions, ToonOptions, XmlOptions, YamlOptions,
)

__version__ = "0.2.0"

__all__ = [
    "Yq", "compile", "dump", "evaluate", "evaluate_all", "load", "query", "update",
    "Expression", "Kind", "Node", "Style",
    "EvaluationError", "EvaluationLimitError", "ExpressionSyntaxError", "FormatError",
    "SecurityError", "UnknownFormatError", "YamlSyntaxError", "YqError",
    "CsvOptions", "JsonOptions", "Limits", "Options", "PropertiesOptions", "SchemaOptions",
    "SecurityPolicy", "TomlOptions", "ToonOptions", "XmlOptions", "YamlOptions",
    "__version__",
]
