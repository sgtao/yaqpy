"""実行ログ（成功した変換の記録）の組み立て・読み戻し・保存先の整理。Flet 非依存。v0.7.0。

1 回の実行（成功）＝ 1 ファイル。ファイルは YAML の**複数文書（``---`` 区切り）** 4 つで、
人が目で読める：

1. 概要（summary）：日時・版・入出力の形式・入力ファイルの情報・設定・再実行できるか
2. 式（expression）：``# expression`` のコメントのあとに ``expression: "<式の一行表示>"``
3. オリジナル（入力）：入力ファイルごとに、**YAML に変換したデータ**（入力ストリームの文書ごと）
4. 結果（出力）：**YAML に変換した結果**

入力・結果を YAML にして書くので、そのまま元の形式へ戻せるとは限らない（複数行に並ぶスカラーの
結果など）。そこで**書く前に必ず読み戻して検査**し、戻せない項目は原文（``text``）を併記する。
これは v0.7.0 の計画書 6-4 節に従う。

配置とファイル名：``<保存先>/<YYYY>/<MMDD>-<hhmmss>[-N]_<入力形式>-to-<出力形式>_convert-log.yaml``
（一覧はファイル名から作り、中身は開かない）。
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from yaqpy import api
from yaqpy import __version__ as YAQPY_VERSION
from yaqpy.core.model.convert import from_python, to_python
from yaqpy.core.model.node import Kind, Node, Style
from yaqpy.options import Options

LOG_VERSION = 1
"""ログ形式の版。読み戻しの互換判定に使う（未知の版は全文表示だけ。再実行は無効）。"""
DEFAULT_MAX_FILES = 500
DEFAULT_MAX_ENTRY_MIB = 1
HEAD_READ_BYTES = 64 * 1024
"""絞り込みのために、ファイルの先頭から読む最大バイト数（概要と式は先頭の 2 文書）。"""
LOG_SUFFIX = "_convert-log.yaml"

_LOG_NAME = re.compile(
    r"^(?P<mmdd>\d{4})-(?P<hhmmss>\d{6})(?:-(?P<seq>\d+))?"
    r"_(?P<input>[a-z0-9]+)-to-(?P<output>[a-z0-9]+)_convert-log\.yaml$")
_YEAR_DIR = re.compile(r"^\d{4}$")

_IDENTITY = {"", "."}


# ---------------------------------------------------------------------- 記録の内容


@dataclass(frozen=True, slots=True)
class LogInput:
    """記録する入力 1 件。``text`` は画面上の（追加編集を含む）原文。"""

    name: str
    text: str
    path: str | None = None
    edited: bool = False


@dataclass(frozen=True, slots=True)
class LogEntry:
    """1 回の実行の記録に要るものすべて。実行した**その時点**の値を、引数で渡す（6-1 節）。"""

    timestamp: datetime
    expression: str
    inputs: tuple[LogInput, ...]
    input_format: str            # 実際に使った形式（auto なら判定結果）
    input_selected: str          # 画面で選んでいた値（auto／形式名）
    output_format: str
    output_selected: str
    output_text: str
    indent: int
    eval_all: bool
    document_count: int
    elapsed_ms: float
    allow_env: bool
    allow_file: bool
    options: Options = field(default_factory=Options)


@dataclass(frozen=True, slots=True)
class BuiltLog:
    text: str
    input_format: str
    output_format: str
    rerunnable: bool
    inputs_omitted: bool = False
    output_omitted: bool = False


def dedupe_key(entry: LogEntry) -> str:
    """直前の記録との同一判定のキー：式・各入力の名前と本文・形式の選択・インデント・
    ``eval_all``・許可の状態。日時・所要時間・出力は含めない（同じ入力と式なら同じ結果のため）。"""
    h = hashlib.sha256()
    parts = [entry.expression, entry.input_selected, entry.output_selected, str(entry.indent),
             str(entry.eval_all), str(entry.allow_env), str(entry.allow_file)]
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    for item in entry.inputs:
        h.update(item.name.encode("utf-8"))
        h.update(b"\x01")
        h.update(item.text.encode("utf-8"))
        h.update(b"\x02")
    return h.hexdigest()


# ---------------------------------------------------------------------- 組み立て


def _node(value: Any) -> Node:
    return from_python(value)


def _mapping(pairs: list[tuple[str, Node]]) -> Node:
    node = Node.mapping()
    for key, value in pairs:
        node.add_key_value(Node.string(key), value)
    return node


def _sequence(items: list[Node]) -> Node:
    node = Node.sequence()
    for item in items:
        node.add_child(item)
    return node


def _double_quoted(text: str) -> Node:
    return Node.string(text, style=Style.DOUBLE_QUOTED)


def _clean(doc: Node, index: int = 0) -> Node:
    """記録に出し入れする文書を、単独の文書にする：先頭の行内容（``%YAML`` など）を落とし、
    親（ログの木）から切り離して、何番目の文書かを ``index`` にする。

    結果の出力は「文書の番号が変わったら ``---`` を出す」ので、番号を振り直さないと、読み戻した
    複数の文書が区切りなしに連結されてしまう。
    """
    doc = doc.copy()
    doc.leading_content = ""
    doc.parent = None
    doc.key = None
    doc.is_map_key = False
    doc.document_index = index
    return doc


def _has_duplicate_keys(node: Node) -> bool:
    """同じキーが 2 度出てくるマッピングを含むか（``.items[]`` の結果を YAML で出したときなど）。
    重複したキーの YAML はデータとして読めない（後の値だけが残る）ので、原文で記録する。"""
    if node.kind is Kind.MAPPING:
        seen: set[str] = set()
        for key, value in node.map_items():
            if key.value in seen or _has_duplicate_keys(value):
                return True
            seen.add(key.value)
        return False
    if node.kind is Kind.SEQUENCE:
        return any(_has_duplicate_keys(child) for child in node.content)
    return False


def _bytes(text: str) -> int:
    return len(text.encode("utf-8"))


def _norm_lines(text: str) -> list[str]:
    """出力の一致の比較用：改行を LF にし、各行の行末の空白と末尾の空行を無視する。"""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return lines


@dataclass(slots=True)
class _Item:
    """入力 1 件を、記録に書く形にしたもの。"""

    source: LogInput
    format: str
    docs: list[Node] | None = None       # 記録する文書（YAML に変換するもの）。None なら原文か省略
    keep_text: bool = False              # 原文（text）を書く
    omitted: bool = False                # 上限を超えたので本文を省く


def _decode(text: str, fmt: str, options: Options) -> list[Node]:
    docs = [_clean(d, i) for i, d in enumerate(api.load(text, format=fmt, options=options))]
    if any(_has_duplicate_keys(d) for d in docs):
        raise ValueError("duplicate keys")
    return docs


def _input_format_of(source: LogInput, selected: str, entry_format: str, options: Options,
                     single: bool) -> str:
    """入力 1 件の実際の形式。``auto`` のときは、この入力の名前と中身から判定する。"""
    if selected not in ("", "auto"):
        return _canonical(selected)
    if single:
        return _canonical(entry_format)
    from yaqpy.formats.registry import builtin_formats

    return builtin_formats().guess(source.path or source.name, source.text).name


def _canonical(name: str) -> str:
    from yaqpy.formats.registry import builtin_formats

    try:
        return builtin_formats().get(name).name
    except Exception:                                    # noqa: BLE001 - 未知の名前はそのまま
        return name


def _files_document(items: list[_Item]) -> Node:
    files: list[Node] = []
    for item in items:
        pairs: list[tuple[str, Node]] = [("name", _node(item.source.name)),
                                         ("format", _node(item.format))]
        if item.omitted:
            pairs.append(("omitted", _node(True)))
        else:
            if item.docs is not None:
                pairs.append(("documents", _sequence(item.docs)))
            if item.keep_text:
                pairs.append(("text", _node(item.source.text)))
        files.append(_mapping(pairs))
    doc = _mapping([("files", _sequence(files))])
    doc.head_comment = "----- original (input) -----"
    return doc


def _result_document(fmt: str, docs: list[Node] | None, text: str | None, omitted: bool) -> Node:
    pairs: list[tuple[str, Node]] = [("format", _node(fmt))]
    if omitted:
        pairs.append(("omitted", _node(True)))
    elif docs is not None:
        pairs.append(("documents", _sequence(docs)))
    else:
        pairs.append(("text", _node(text or "")))
    doc = _mapping(pairs)
    doc.head_comment = "----- result (output) -----"
    return doc


def _expression_document(expression: str) -> Node:
    used = expression.strip() not in _IDENTITY
    doc = _mapping([("expression", _double_quoted(expression if used else "."))])
    doc.head_comment = "----- expression -----\nexpression" + ("" if used else " (not used)")
    return doc


def _summary_document(entry: LogEntry, items: list[_Item], *, rerunnable: bool,
                      output_bytes: int, representation: dict[str, str]) -> Node:
    files = [{"name": i.source.name, "path": i.source.path, "bytes": _bytes(i.source.text),
              "edited": i.source.edited} for i in items]
    data: dict[str, Any] = {
        "yaqpy_log": LOG_VERSION,
        "yaqpy_version": YAQPY_VERSION,
        "timestamp": entry.timestamp.astimezone().isoformat(timespec="seconds"),
        "input": {"format": entry.input_format, "selected": entry.input_selected, "files": files},
        "output": {"format": entry.output_format, "selected": entry.output_selected,
                   "indent": entry.indent, "bytes": output_bytes},
        "eval_all": entry.eval_all,
        "document_count": entry.document_count,
        "elapsed_ms": round(entry.elapsed_ms, 1),
        "security": {"allow_env": entry.allow_env, "allow_file": entry.allow_file},
        "rerunnable": rerunnable,
    }
    if representation:
        data["representation"] = representation
    doc = _node(data)
    doc.head_comment = "----- summary -----"
    return doc


def _join(docs: list[Node]) -> str:
    """4 つの文書を YAML として書き、``---`` でつなぐ（1 文書ずつ書くので、文書の区切りは自前）。"""
    parts = [api.dump([d], format="yaml", options=Options()) for d in docs]
    return "---\n".join(p if p.endswith("\n") else p + "\n" for p in parts)


def build_log(entry: LogEntry, *, max_entry_bytes: int = DEFAULT_MAX_ENTRY_MIB * 1024 * 1024
              ) -> BuiltLog:
    """記録するファイルの全文を組み立てる。

    書く前に、できあがった全文を ``parse_log_text`` で読み戻して検査する（6-4 節）：
    式が完全に同じか、入力が元の形式へ戻せるか、結果が元の出力と同じか。戻せない項目は
    ``documents`` をやめて原文（``text``）にし、概要の ``representation`` に残す。
    """
    options = entry.options
    single = len(entry.inputs) == 1
    items = [_Item(source=s, format=_input_format_of(s, entry.input_selected, entry.input_format,
                                                     options, single))
             for s in entry.inputs]
    inputs_omitted = sum(_bytes(s.text) for s in entry.inputs) > max_entry_bytes
    output_bytes = _bytes(entry.output_text)
    output_omitted = output_bytes > max_entry_bytes
    representation: dict[str, str] = {}

    if inputs_omitted:
        for item in items:
            item.omitted = True
    else:
        for i, item in enumerate(items):
            try:
                item.docs = _decode(item.source.text, item.format, options)
            except Exception:                            # noqa: BLE001 - 読めなければ原文を書く
                item.docs, item.keep_text = None, True
                representation[f"input_{i}"] = "text"

    result_format = _canonical(entry.output_format)
    result_docs: list[Node] | None = None
    result_text: str | None = None
    if not output_omitted:
        try:
            result_docs = _decode(entry.output_text, result_format, options)
        except Exception:                                # noqa: BLE001
            result_docs, result_text = None, entry.output_text
            representation["output"] = "text"

    def compose(rerunnable: bool) -> str:
        return _join([
            _summary_document(entry, items, rerunnable=rerunnable, output_bytes=output_bytes,
                              representation=representation),
            _expression_document(entry.expression),
            _files_document(items),
            _result_document(result_format, result_docs, result_text, output_omitted),
        ])

    # 検査で戻せなかった項目を原文に切り替えながら、収束するまで（多くても 2 回）組み直す
    rerunnable = not inputs_omitted
    text = compose(rerunnable)
    for _ in range(2):
        problems = _verify(entry, parse_log_text(text), items, result_docs, result_format,
                           options, output_omitted)
        if not problems.any():
            break
        if problems.expression:
            # 式が戻らない（想定外）：全文は残すが、再実行させない
            rerunnable = False
            representation["expression"] = "unreliable"
        for index in problems.inputs:
            items[index].docs, items[index].keep_text = None, True
            representation[f"input_{index}"] = "text"
        if problems.output and result_docs is not None:
            result_docs, result_text = None, entry.output_text
            representation["output"] = "text"
        text = compose(rerunnable)
    return BuiltLog(text=text, input_format=_canonical(entry.input_format),
                    output_format=result_format, rerunnable=rerunnable,
                    inputs_omitted=inputs_omitted, output_omitted=output_omitted)


@dataclass(slots=True)
class _Problems:
    expression: bool = False
    inputs: list[int] = field(default_factory=list)
    output: bool = False

    def any(self) -> bool:
        return self.expression or bool(self.inputs) or self.output


def _verify(entry: LogEntry, parsed: ParsedLog, items: list[_Item], result_docs: list[Node] | None,
            result_format: str, options: Options, output_omitted: bool) -> _Problems:
    problems = _Problems()
    if not parsed.ok or parsed.expression != (entry.expression if entry.expression.strip()
                                              not in _IDENTITY else "."):
        problems.expression = True
        return problems
    for index, item in enumerate(items):
        if item.docs is None:
            continue
        restored = parsed.inputs[index].docs if index < len(parsed.inputs) else None
        if restored is None or not _same_documents(item.docs, restored):
            problems.inputs.append(index)
            continue
        try:                                             # 元の形式へ戻して、もう一度読んで同じか
            back = api.load(api.dump(restored, format=item.format, options=options),
                            format=item.format, options=options)
        except Exception:                                # noqa: BLE001
            problems.inputs.append(index)
            continue
        if not _same_documents(item.docs, back):
            problems.inputs.append(index)
    if result_docs is not None and not output_omitted:
        restored_result = parsed.result.docs if parsed.result is not None else None
        try:
            ok = (restored_result is not None
                  and _same_documents(result_docs, restored_result)
                  and _norm_lines(api.dump(restored_result, format=result_format, options=options))
                  == _norm_lines(entry.output_text))
        except Exception:                                # noqa: BLE001
            ok = False
        if not ok:
            problems.output = True
    return problems


def _same_documents(a: list[Node], b: list[Node]) -> bool:
    if len(a) != len(b):
        return False
    try:
        return all(to_python(x) == to_python(y) for x, y in zip(a, b, strict=True))
    except Exception:                                    # noqa: BLE001
        return False


# ---------------------------------------------------------------------- 読み戻し


@dataclass(slots=True)
class ParsedInput:
    name: str
    format: str = ""
    path: str | None = None
    edited: bool = False
    docs: list[Node] | None = None
    text: str | None = None
    omitted: bool = False


@dataclass(slots=True)
class ParsedResult:
    format: str = ""
    docs: list[Node] | None = None
    text: str | None = None
    omitted: bool = False


@dataclass(slots=True)
class ParsedLog:
    """``parse_log_text`` の結果。``ok`` が偽なら ``error`` に理由（全文表示だけ行う）。"""

    ok: bool = False
    error: str = ""
    version: int = 0
    summary: dict[str, Any] = field(default_factory=dict)
    expression: str = ""
    inputs: list[ParsedInput] = field(default_factory=list)
    result: ParsedResult | None = None

    @property
    def known_version(self) -> bool:
        return self.version == LOG_VERSION

    @property
    def rerunnable(self) -> bool:
        """再実行できるか：読めて、既知の版で、概要が再実行可とし、すべての入力が復元できる。"""
        return (self.ok and self.known_version and bool(self.summary.get("rerunnable"))
                and bool(self.inputs)
                and all(not i.omitted and (i.docs is not None or i.text is not None)
                        for i in self.inputs))


def _get(node: Node | None, key: str) -> Node | None:
    if node is None or node.kind is not Kind.MAPPING:
        return None
    return node.get_map_value(key)


def _scalar(node: Node | None, default: str = "") -> str:
    if node is None or node.kind is not Kind.SCALAR:
        return default
    value = to_python(node)
    return default if value is None else str(value)


def parse_log_text(text: str) -> ParsedLog:
    """ログの全文を読み戻す。壊れていても例外にせず、``ok=False`` と理由で返す。"""
    try:
        docs = api.load(text, format="yaml")
    except Exception as e:                               # noqa: BLE001
        return ParsedLog(error=str(e))
    if len(docs) < 2:
        return ParsedLog(error="not a yaqpy run log")
    summary_node, expression_node = docs[0], docs[1]
    if summary_node.kind is not Kind.MAPPING:
        return ParsedLog(error="not a yaqpy run log")
    try:
        summary = to_python(summary_node)
    except Exception as e:                               # noqa: BLE001
        return ParsedLog(error=str(e))
    version = summary.get("yaqpy_log")
    parsed = ParsedLog(ok=True, version=version if isinstance(version, int) else 0,
                       summary=summary)
    expression = _get(expression_node, "expression")
    if expression is None:
        return ParsedLog(error="the expression document is missing", version=parsed.version,
                         summary=summary)
    parsed.expression = _scalar(expression)
    if len(docs) >= 3:
        files = _get(docs[2], "files")
        parsed.inputs = _parse_inputs(files, summary)
    if len(docs) >= 4:
        parsed.result = _parse_result(docs[3])
    return parsed


def _parse_inputs(files: Node | None, summary: dict[str, Any]) -> list[ParsedInput]:
    out: list[ParsedInput] = []
    if files is None or files.kind is not Kind.SEQUENCE:
        return out
    meta = (summary.get("input") or {}).get("files") or []
    for index, file_node in enumerate(files.content):
        info = meta[index] if index < len(meta) and isinstance(meta[index], dict) else {}
        item = ParsedInput(name=_scalar(_get(file_node, "name")),
                           format=_scalar(_get(file_node, "format")),
                           path=info.get("path"), edited=bool(info.get("edited")))
        item.omitted = bool(_scalar(_get(file_node, "omitted")) == "True")
        documents = _get(file_node, "documents")
        if documents is not None and documents.kind is Kind.SEQUENCE:
            item.docs = [_clean(d, i) for i, d in enumerate(documents.content)]
        text_node = _get(file_node, "text")
        if text_node is not None:
            item.text = _scalar(text_node)
        out.append(item)
    return out


def _parse_result(node: Node) -> ParsedResult:
    result = ParsedResult(format=_scalar(_get(node, "format")))
    result.omitted = bool(_scalar(_get(node, "omitted")) == "True")
    documents = _get(node, "documents")
    if documents is not None and documents.kind is Kind.SEQUENCE:
        result.docs = [_clean(d, i) for i, d in enumerate(documents.content)]
    text_node = _get(node, "text")
    if text_node is not None:
        result.text = _scalar(text_node)
    return result


def restore_input_text(item: ParsedInput, options: Options | None = None) -> str:
    """ログの入力 1 件を、記録した元の形式のテキストへ戻す（再実行用）。原文があれば原文。"""
    if item.text is not None:
        return item.text
    if item.docs is None:
        raise ValueError(f"the input {item.name!r} was not recorded")
    return api.dump(item.docs, format=item.format or "yaml", options=options or Options())


@dataclass(frozen=True, slots=True)
class LogHead:
    """一覧の絞り込み用に、ファイルの先頭（概要と式）だけから取り出した情報。"""

    expression: str = ""
    input_names: tuple[str, ...] = ()
    rerunnable: bool = False


def read_head(path: str | Path, max_bytes: int = HEAD_READ_BYTES) -> LogHead:
    """ファイルの先頭部分だけを読み、概要と式を取り出す（3 つ目の ``---`` の手前まで）。"""
    try:
        with open(path, "rb") as f:
            raw = f.read(max_bytes)
    except OSError:
        return LogHead()
    text = raw.decode("utf-8", errors="ignore")
    parts = re.split(r"^---[ \t]*$", text, maxsplit=3, flags=re.MULTILINE)
    head = "---\n".join(parts[:2])
    parsed = parse_log_text(head)
    if not parsed.summary:
        return LogHead()
    files = (parsed.summary.get("input") or {}).get("files") or []
    names = tuple(str(f.get("name", "")) for f in files if isinstance(f, dict))
    return LogHead(expression=parsed.expression, input_names=names,
                   rerunnable=bool(parsed.summary.get("rerunnable")))


# ---------------------------------------------------------------------- 保存先・ファイル名


def default_log_dir(platform: str | None = None, environ: Mapping[str, str] | None = None) -> str:
    """OS 別の既定の保存先（依存ゼロのため ``platformdirs`` は使わない）。

    * Windows：``%LOCALAPPDATA%\\yaqpy\\logs``（Roaming の ``%APPDATA%`` はドメイン環境で同期される
      ので、容量の大きいログは Local に置く）
    * macOS：``~/Library/Logs/yaqpy``
    * それ以外：``$XDG_STATE_HOME/yaqpy/logs``（未設定なら ``~/.local/state/yaqpy/logs``）
    """
    platform = sys.platform if platform is None else platform
    env = os.environ if environ is None else environ
    home = env.get("USERPROFILE") or env.get("HOME") or os.path.expanduser("~")
    if platform.startswith("win"):
        base = env.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        return os.path.join(base, "yaqpy", "logs")
    if platform == "darwin":
        return os.path.join(home, "Library", "Logs", "yaqpy")
    state = env.get("XDG_STATE_HOME") or os.path.join(home, ".local", "state")
    return os.path.join(state, "yaqpy", "logs")


def log_file_name(timestamp: datetime, input_format: str, output_format: str,
                  seq: int = 0) -> str:
    """``MMDD-hhmmss[-N]_<入力>-to-<出力>_convert-log.yaml``（日時はローカル時刻。年はフォルダ）。"""
    stamp = timestamp.strftime("%m%d-%H%M%S")
    suffix = f"-{seq}" if seq > 1 else ""
    return f"{stamp}{suffix}_{_slug(input_format)}-to-{_slug(output_format)}{LOG_SUFFIX}"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower()) or "unknown"


@dataclass(frozen=True, slots=True)
class LogFile:
    """一覧の 1 行（ファイル名と ``os.stat`` から作る。中身は開かない）。"""

    path: str
    year: int
    mmdd: str
    hhmmss: str
    seq: int
    input_format: str
    output_format: str
    size: int

    @property
    def sort_key(self) -> tuple[int, str, str, int]:
        return (self.year, self.mmdd, self.hhmmss, self.seq)

    @property
    def timestamp_text(self) -> str:
        """``2026-09-23 14:05:12`` の形。"""
        h = self.hhmmss
        return f"{self.year:04d}-{self.mmdd[:2]}-{self.mmdd[2:]} {h[:2]}:{h[2:4]}:{h[4:]}"


def parse_log_file_name(name: str) -> tuple[str, str, int, str, str] | None:
    """ファイル名を読む。戻り値は (mmdd, hhmmss, 連番, 入力形式, 出力形式)。合わなければ None。"""
    m = _LOG_NAME.match(name)
    if m is None:
        return None
    return (m["mmdd"], m["hhmmss"], int(m["seq"] or 1), m["input"], m["output"])


def unique_log_path(root: str | Path, timestamp: datetime, input_format: str,
                    output_format: str) -> Path:
    """書き込む先のパス。同じ秒に 2 件目ができたら連番を付ける（まず起きない）。"""
    directory = Path(root) / f"{timestamp.year:04d}"
    seq = 1
    while True:
        path = directory / log_file_name(timestamp, input_format, output_format, seq)
        if not path.exists():
            return path
        seq += 1


def list_log_files(root: str | Path) -> list[LogFile]:
    """保存先の年フォルダを走査して、ログの名前に合うファイルを新しい順に返す。"""
    base = Path(root)
    found: list[LogFile] = []
    try:
        year_dirs = [d for d in base.iterdir() if d.is_dir() and _YEAR_DIR.match(d.name)]
    except OSError:
        return []
    for year_dir in year_dirs:
        try:
            entries = list(year_dir.iterdir())
        except OSError:
            continue
        for path in entries:
            parsed = parse_log_file_name(path.name)
            if parsed is None or not path.is_file():
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            mmdd, hhmmss, seq, input_format, output_format = parsed
            found.append(LogFile(path=str(path), year=int(year_dir.name), mmdd=mmdd,
                                 hhmmss=hhmmss, seq=seq, input_format=input_format,
                                 output_format=output_format, size=size))
    found.sort(key=lambda f: f.sort_key, reverse=True)
    return found


def prune_logs(root: str | Path, max_files: int) -> int:
    """件数が上限を超えていたら、古いものから削除する。空になった年フォルダも消す。

    ログの名前に合うファイルだけが対象で、利用者が置いた別のファイルは消さない。
    戻り値は削除した件数。
    """
    if max_files <= 0:
        return 0
    files = list_log_files(root)
    removed = 0
    for old in files[max_files:]:
        if _remove(old.path):
            removed += 1
    _remove_empty_year_dirs(root)
    return removed


def delete_log(path: str | Path) -> bool:
    """ログ 1 件を削除する（ログの名前に合わないものは消さない）。"""
    if parse_log_file_name(Path(path).name) is None:
        return False
    removed = _remove(path)
    _remove_empty_year_dirs(Path(path).parent.parent)
    return removed


def delete_all_logs(root: str | Path) -> int:
    """ログの名前に合うファイルをすべて削除する。戻り値は削除した件数。"""
    removed = sum(1 for f in list_log_files(root) if _remove(f.path))
    _remove_empty_year_dirs(root)
    return removed


def _remove(path: str | Path) -> bool:
    try:
        Path(path).unlink()
    except OSError:
        return False
    return True


def _remove_empty_year_dirs(root: str | Path) -> None:
    try:
        for d in Path(root).iterdir():
            if d.is_dir() and _YEAR_DIR.match(d.name) and not any(d.iterdir()):
                d.rmdir()
    except OSError:
        pass


def write_log(root: str | Path, entry: LogEntry, built: BuiltLog,
              write: Callable[[str, str], None]) -> str:
    """ログを 1 ファイル書く。``write(path, text)`` は、親フォルダを作って書く関数
    （``LocalFileSystem.write_file``）。戻り値は書いたパス。"""
    path = unique_log_path(root, entry.timestamp, built.input_format, built.output_format)
    write(str(path), built.text)
    return str(path)
