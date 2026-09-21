"""Worked examples for ``--example``, ``--guide-prompt`` and ``--skill-md``.

Every example is *run* when it is shown: what is printed is the output of the real engine, never a
hand-typed answer. ``expected`` pins that output, and a test compares the two, so an example can
not go stale without the test noticing.
"""

from __future__ import annotations

from dataclasses import dataclass

from yaqpy.app.dto import EvalMode, EvaluateRequest, InputSource
from yaqpy.app.printer import MemorySink
from yaqpy.app.recipe_service import RecipeService
from yaqpy.app.recipe_text import summary_lines
from yaqpy.app.service import YqService, with_prune
from yaqpy.options import Options, SecurityPolicy

SHOP_YAML = """\
server:
  host: localhost
  port: 8080
items:
  - {name: pen, price: 120, tags: [a, b]}
  - {name: cap, price: 80, tags: []}
  - {name: bag, price: 300, tags: [b]}
"""

OPENAI_REQUEST = """\
{
  "model": "gpt-4o",
  "messages": [
    {"role": "system", "content": "You are helpful."},
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi!"}
  ],
  "temperature": 0.7,
  "max_completion_tokens": 256,
  "stop": "END",
  "stream": true
}
"""


@dataclass(frozen=True, slots=True)
class Example:
    title: str
    input: str
    input_name: str                 # what the file is called in the command line shown
    expected: str                   # the output the example must give (pinned by a test)
    expression: str = ""
    flags: str = ""                 # shown before the expression, e.g. "-o json"
    input_format: str = "yaml"
    output_format: str = "yaml"
    eval_all: bool = False
    prune_null: bool = False
    prune_empty: bool = False
    recipe: str = ""                # run this bundled recipe instead of an expression
    expected_notes: tuple[str, ...] = ()

    @property
    def command(self) -> str:
        if self.recipe:
            return " ".join(["yaqpy", "--recipe", self.recipe] + ([self.flags] if self.flags else [])
                            + [self.input_name])
        parts = ["yaqpy"]
        if self.eval_all:
            parts.append("eval-all")
        if self.flags:
            parts.append(self.flags)
        if self.prune_null:
            parts.append("--prune-null")
        if self.prune_empty:
            parts.append("--prune-empty")
        if self.expression:
            parts.append("'" + self.expression + "'")
        parts.append(self.input_name)
        return " ".join(parts)


EXAMPLES: tuple[Example, ...] = (
    Example("値を取り出す", SHOP_YAML, "shop.yaml", "8080\n", ".server.port"),
    Example("条件で絞り込む", SHOP_YAML, "shop.yaml", "pen\nbag\n",
            ".items[] | select(.price > 100) | .name"),
    Example("値を更新する（更新したファイルにしたいときは -i を付ける）", SHOP_YAML, "shop.yaml",
            "host: localhost\nport: 9090\n", ".server.port = 9090 | .server"),
    Example("JSON に変換して整える", SHOP_YAML, "shop.yaml", '["pen","cap","bag"]\n',
            ".items | map(.name)", flags="-o json -I 0", output_format="json"),
    Example("合計を求める（jq の reduce は ireduce）", SHOP_YAML, "shop.yaml", "500\n",
            ".items | .[] as $i ireduce (0; . + $i.price)"),
    Example("並べ替える", SHOP_YAML, "shop.yaml", "bag\n",
            ".items | sort_by(.price) | reverse | .[0].name"),
    Example("文字列をつなぐ", SHOP_YAML, "shop.yaml", "pen, cap, bag\n",
            '[.items[].name] | join(", ")'),
    Example("条件に合う要素だけを更新する（要素の中の値で書き換えるときは |=）", SHOP_YAML, "shop.yaml",
            "[120,100,300]\n", "(.items[] | select(.price < 100)) |= (.price = 100) | .items | map(.price)",
            flags="-o json -I 0", output_format="json"),
    Example("表（CSV）に変える", SHOP_YAML, "shop.yaml", "name,price\npen,120\ncap,80\nbag,300\n",
            '.items | map(pick(["name", "price"]))', flags="-o csv", output_format="csv"),
    Example("キーがあるときだけ代入する（select は代入の左辺の先頭に置く）", SHOP_YAML, "shop.yaml",
            "port: 8080\n", "(select(.server.port != null) | .backup.port) = .server.port | .backup"),
    Example("2 つの文書を 1 つに重ねる", "a: 1\nb: 1\n---\nb: 2\nc: 3\n", "two.yaml",
            "a: 1\nb: 2\nc: 3\n", ". as $doc ireduce ({}; . * $doc)", eval_all=True),
    Example("データの形（JSON Schema）を出す — yaqpy 独自", SHOP_YAML, "shop.yaml",
            '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object",'
            '"properties":{"server":{"type":"object","properties":{"host":{"type":"string"},'
            '"port":{"type":"integer"}},"required":["host","port"]},"items":{"type":"array",'
            '"items":{"type":"object","properties":{"name":{"type":"string"},"price":{"type":"integer"},'
            '"tags":{"type":"array","items":{"type":"string"}}},"required":["name","price","tags"]}}},'
            '"required":["server","items"]}\n',
            "schema", flags="-o json -I 0", output_format="json"),
    Example("null と空の入れ物を取り除く — yaqpy 独自", '{"a": null, "b": {"c": null}, "d": 1}\n',
            "in.json", '{"d":1}\n', "", flags="-o json -I 0", input_format="json",
            output_format="json", prune_null=True, prune_empty=True),
    Example("API のリクエストを変換する（レシピ）— yaqpy 独自", OPENAI_REQUEST, "request.json",
            '{"systemInstruction":{"parts":[{"text":"You are helpful."}]},'
            '"contents":[{"role":"user","parts":[{"text":"Hello"}]},{"role":"model","parts":[{"text":"Hi!"}]}],'
            '"generationConfig":{"temperature":0.7,"maxOutputTokens":256,"stopSequences":["END"]}}\n',
            input_format="json", output_format="json", recipe="openai-to-gemini", flags="-I 0",
            expected_notes=("dropped .model", "dropped .stream")),
)


def run_example(service: YqService, example: Example) -> tuple[str, list[str]]:
    """Run an example on the real engine. Returns the output and, for a recipe, the notes it printed."""
    options = Options(input_format=example.input_format, output_format=example.output_format,
                      indent=0 if "-I 0" in example.flags else 2, security=SecurityPolicy.strict())
    if example.recipe:
        recipes = RecipeService(service)
        recipe = recipes.load(example.recipe)
        run = recipes.run(recipe, InputSource("<text>", example.input), options,
                          input_format="json", output_format="json")
        return run.output, summary_lines(run)
    expression = with_prune(example.expression or ".", nulls=example.prune_null,
                            empties=example.prune_empty) if (example.prune_null or example.prune_empty) \
        else example.expression
    request = EvaluateRequest(
        expression=expression, inputs=(InputSource("<text>", example.input),),
        mode=EvalMode.ALL if example.eval_all else EvalMode.STREAM, options=options,
        input_format=example.input_format, output_format=example.output_format)
    result = service.evaluate(request, MemorySink())
    return result.output or "", []
