"""FormatSpec / FormatRegistry (design doc 9-1)."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from yaqpy.errors import UnknownFormatError
from yaqpy.formats.sniff import detect_format
from yaqpy.options import Options


@dataclass(frozen=True, slots=True)
class FormatSpec:
    name: str
    aliases: tuple[str, ...] = ()
    extensions: tuple[str, ...] = ()
    decoder_factory: Callable[[Options], Any] | None = None
    encoder_factory: Callable[[Options, bool], Any] | None = None
    unwrap_scalar_default: bool = False

    def matches(self, name: str) -> bool:
        return name == self.name or name in self.aliases


class FormatRegistry:
    def __init__(self) -> None:
        self._specs: list[FormatSpec] = []
        self._frozen = False

    def register(self, spec: FormatSpec) -> None:
        if self._frozen:
            raise RuntimeError("registry is frozen; call copy() to extend it")
        self._specs = [s for s in self._specs if s.name != spec.name]
        self._specs.append(spec)

    def freeze(self) -> FormatRegistry:
        self._frozen = True
        return self

    def copy(self) -> FormatRegistry:
        new = FormatRegistry()
        new._specs = list(self._specs)
        return new

    def get(self, name_or_alias: str) -> FormatSpec:
        for spec in self._specs:
            if spec.matches(name_or_alias):
                return spec
        raise UnknownFormatError(
            f"unknown format '{name_or_alias}' please use [{self.available_string()}]",
            format=name_or_alias,
        )

    def available_string(self) -> str:
        names: list[str] = []
        for spec in self._specs:
            if spec.encoder_factory is not None:
                names.append(spec.name)
                if spec.aliases:
                    names.append(spec.aliases[0])
        return "|".join(names)

    def guess_from_filename(self, filename: str) -> FormatSpec | None:
        """The format the extension names, or None when there is no extension or it is unknown."""
        if filename:
            ext = os.path.splitext(filename)[1]
            if len(ext) >= 2 and ext.startswith("."):
                name = ext[1:].lower()
                for spec in self._specs:
                    if spec.matches(name) or name in [e.lstrip(".") for e in spec.extensions]:
                        return spec
        return None

    def from_filename(self, filename: str) -> FormatSpec:
        """Guess from the extension; unknown extensions default to yaml (Go behaviour)."""
        return self.guess_from_filename(filename) or self.get("yaml")

    def guess(self, filename: str, text: str) -> FormatSpec:
        """Guess a format (a yaqpy extension: Go yq only ever looks at the extension).

        The extension wins first, exactly like ``from_filename`` - this never changes behaviour for
        a file whose extension already names a format. Only when the extension gives no answer (no
        extension, an unknown one, or piped/pasted text with no name) is the content itself looked
        at; when that is inconclusive too, ``yaml`` is the fallback, same as it always was.
        """
        found = self.guess_from_filename(filename)
        if found is not None:
            return found
        detected = detect_format(text)
        if detected is not None:
            spec = next((s for s in self._specs if s.name == detected), None)
            if spec is not None and spec.decoder_factory is not None:
                return spec
        return self.get("yaml")

    def input_formats(self) -> list[str]:
        return [s.name for s in self._specs if s.decoder_factory is not None]

    def output_formats(self) -> list[str]:
        return [s.name for s in self._specs if s.encoder_factory is not None]

    def input_extensions(self) -> list[str]:
        """File extensions (without the dot) of every format that can be read.

        The GUI's "open" dialog uses this, so a newly registered input format shows up there
        without a second table.
        """
        out: list[str] = []
        for spec in self._specs:
            if spec.decoder_factory is None:
                continue
            for ext in spec.extensions:
                name = ext.lstrip(".")
                if name not in out:
                    out.append(name)
        return out

    def all_names(self) -> list[str]:
        names: list[str] = []
        for spec in self._specs:
            names.append(spec.name)
            names.extend(spec.aliases)
        return names

    def decoder_for(self, name: str, options: Options) -> Any:
        spec = self.get(name)
        if spec.decoder_factory is None:
            raise UnknownFormatError(f"no support for {name} input format", format=name)
        return spec.decoder_factory(options)

    def encoder_for(self, name: str, options: Options, unwrap_scalar: bool) -> Any:
        spec = self.get(name)
        if spec.encoder_factory is None:
            raise UnknownFormatError(f"no support for {name} output format", format=name)
        return spec.encoder_factory(options, unwrap_scalar)


_builtin: FormatRegistry | None = None


def builtin_formats() -> FormatRegistry:
    global _builtin
    if _builtin is None:
        from yaqpy.formats.csv_codec import CsvDecoder, CsvEncoder
        from yaqpy.formats.json_codec import JsonDecoder, JsonEncoder
        from yaqpy.formats.props_codec import PropertiesDecoder, PropertiesEncoder
        from yaqpy.formats.toml_codec import TomlDecoder, TomlEncoder
        from yaqpy.formats.toon_codec import ToonDecoder, ToonEncoder
        from yaqpy.formats.xml_codec import XmlDecoder, XmlEncoder
        from yaqpy.formats.yaml.codec import YamlDecoder, YamlEncoder

        reg = FormatRegistry()
        reg.register(FormatSpec(
            "yaml", ("y", "yml"), (".yaml", ".yml"),
            decoder_factory=lambda o: YamlDecoder(o),
            encoder_factory=lambda o, u: YamlEncoder(o, unwrap_scalar=u),
            unwrap_scalar_default=True,
        ))
        reg.register(FormatSpec(
            "json", ("j",), (".json",),
            decoder_factory=lambda o: JsonDecoder(o),
            encoder_factory=lambda o, u: JsonEncoder(o, unwrap_scalar=u),
            unwrap_scalar_default=False,
        ))
        reg.register(FormatSpec(
            "props", ("p", "properties"), (".properties",),
            decoder_factory=lambda o: PropertiesDecoder(o),
            encoder_factory=lambda o, u: PropertiesEncoder(o, unwrap_scalar=u),
            unwrap_scalar_default=True,
        ))
        reg.register(FormatSpec(
            "toon", (), (".toon",),
            decoder_factory=lambda o: ToonDecoder(o),
            encoder_factory=lambda o, u: ToonEncoder(o, unwrap_scalar=u),
            unwrap_scalar_default=False,
        ))
        reg.register(FormatSpec(
            "xml", ("x",), (".xml",),
            decoder_factory=lambda o: XmlDecoder(o),
            encoder_factory=lambda o, u: XmlEncoder(o, unwrap_scalar=u),
            unwrap_scalar_default=False,
        ))
        reg.register(FormatSpec(
            "csv", ("c",), (".csv",),
            decoder_factory=lambda o: CsvDecoder(o),
            encoder_factory=lambda o, u: CsvEncoder(o, unwrap_scalar=u),
            unwrap_scalar_default=False,
        ))
        reg.register(FormatSpec(
            "tsv", ("t",), (".tsv",),
            decoder_factory=lambda o: CsvDecoder(o, tsv=True),
            encoder_factory=lambda o, u: CsvEncoder(o, tsv=True, unwrap_scalar=u),
            unwrap_scalar_default=False,
        ))
        reg.register(FormatSpec(
            "toml", (), (".toml",),
            decoder_factory=lambda o: TomlDecoder(o),
            encoder_factory=lambda o, u: TomlEncoder(o, unwrap_scalar=u),
            unwrap_scalar_default=False,
        ))
        _builtin = reg.freeze()
    return _builtin
