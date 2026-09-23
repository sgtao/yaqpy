"""yaqpy - a pure-Python (standard library only) implementation of mikefarah/yq.

>>> import yaqpy
>>> yaqpy.evaluate(".a.b", "a:\\n  b: 3\\n")
'3\\n'
>>> yaqpy.query(".items[] | select(. > 1)", {"items": [1, 2, 3]})
[2, 3]
"""

from yaqpy.api import (
    Yq, apply_recipe, compile, detect_format, dump, evaluate, evaluate_all, list_recipes, load,
    query, update,
)
from yaqpy.app.recipe_service import RecipeRun
from yaqpy.core.lang.parser import Expression
from yaqpy.core.model.node import Kind, Node, Style
from yaqpy.errors import (
    EvaluationError, EvaluationLimitError, ExpressionSyntaxError, FormatError, RecipeError,
    SecurityError, UnknownFormatError, YamlSyntaxError, YqError,
)
from yaqpy.options import (
    CsvOptions, JsonOptions, Limits, Options, PropertiesOptions, SchemaOptions, SecurityPolicy,
    TomlOptions, ToonOptions, XmlOptions, YamlOptions,
)
from yaqpy.recipes import Recipe, build_recipe
from yaqpy.recipes.analysis import RecipeReport

__version__ = "0.6.0"

__all__ = [
    "Yq", "compile", "dump", "evaluate", "evaluate_all", "load", "query", "update",
    "apply_recipe", "list_recipes", "build_recipe", "Recipe", "RecipeReport", "RecipeRun",
    "detect_format",
    "Expression", "Kind", "Node", "Style",
    "EvaluationError", "EvaluationLimitError", "ExpressionSyntaxError", "FormatError", "RecipeError",
    "SecurityError", "UnknownFormatError", "YamlSyntaxError", "YqError",
    "CsvOptions", "JsonOptions", "Limits", "Options", "PropertiesOptions", "SchemaOptions",
    "SecurityPolicy", "TomlOptions", "ToonOptions", "XmlOptions", "YamlOptions",
    "__version__",
]
