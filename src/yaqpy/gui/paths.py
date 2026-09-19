"""読み込んだ文書から、プルダウンに出すプロパティパスの候補を作る。

現行 yaqpy に ``paths`` 演算子が無い（``path`` と ``del_paths`` のみ）ため、
Node ツリーを Python 側で走査する。評価器は通さないので副作用はない。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from yaqpy.core.model.node import Kind, Node

MAP = "map"
SEQ = "seq"
SCALAR = "scalar"
ALIAS = "alias"

MERGE_KEY = "<<"
SAMPLE_MAX = 40

DEFAULT_MAX_DEPTH = 6
DEFAULT_MAX_ITEMS = 500

# 素のまま `.key` と書いて安全なキー（詳しくは Phase G2 プラン 2-1）
_BARE_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")

_KIND_NAMES = {Kind.MAPPING: MAP, Kind.SEQUENCE: SEQ, Kind.ALIAS: ALIAS}


@dataclass(frozen=True, slots=True)
class PathCandidate:
    expression: str        # ".server.port" / ".items[]" / '.["my key"]'
    kind: str              # "map" | "seq" | "scalar" | "alias"
    sample: str = ""       # スカラーのときだけ、値の先頭
    depth: int = 1

    @property
    def label(self) -> str:
        """プルダウンに出す 1 行。"""
        if self.kind == SCALAR and self.sample:
            return f"{self.expression}  = {self.sample}"
        return f"{self.expression}  ({self.kind})"


def format_key(key: str) -> str:
    """マッピングのキー 1 つを、パス式の 1 区間に変換する。"""
    if _BARE_KEY.fullmatch(key):
        return f".{key}"
    escaped = key.replace("\\", "\\\\").replace('"', '\\"')
    return f'.["{escaped}"]'


def _kind_of(node: Node) -> str:
    return _KIND_NAMES.get(node.kind, SCALAR)


def _sample_of(node: Node) -> str:
    if node.kind is not Kind.SCALAR:
        return ""
    value = node.value.replace("\n", " ").strip()
    return value if len(value) <= SAMPLE_MAX else value[: SAMPLE_MAX - 1] + "…"


def collect_paths(documents: Sequence[Node], *, max_depth: int = DEFAULT_MAX_DEPTH,
                  max_items: int = DEFAULT_MAX_ITEMS) -> list[PathCandidate]:
    """文書を深さ優先で走査して、パス候補を文書の出現順に返す。

    - シーケンスは要素ごとに展開せず ``[]`` に畳み、構造は**先頭要素**を代表にする
    - エイリアス（``*name``）と マージキー（``<<``）は辿らない（無限ループ防止）
    - 同じ式は 1 回だけ
    """
    out: list[PathCandidate] = []
    seen: set[str] = set()

    def emit(expression: str, node: Node, depth: int) -> bool:
        """候補を 1 件足す。上限に達したら False を返して走査を止める。"""
        if expression in seen:
            return True
        if len(out) >= max_items:
            return False
        seen.add(expression)
        out.append(PathCandidate(expression, _kind_of(node), _sample_of(node), depth))
        return True

    def walk(node: Node, prefix: str, depth: int) -> None:
        if depth > max_depth or len(out) >= max_items:
            return
        if node.kind is Kind.MAPPING:
            for key, value in node.map_items():
                if key.value == MERGE_KEY:
                    continue
                expression = prefix + format_key(key.value)
                if not emit(expression, value, depth):
                    return
                if value.kind is not Kind.ALIAS:
                    walk(value, expression, depth + 1)
        elif node.kind is Kind.SEQUENCE:
            if not node.content:
                return
            expression = prefix + "[]"
            first = node.content[0]
            if not emit(expression, first, depth):
                return
            if first.kind is not Kind.ALIAS:
                walk(first, expression, depth + 1)

    for document in documents:
        walk(document, "", 1)
    return out
