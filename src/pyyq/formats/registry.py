"""FormatSpec / FormatRegistry (design doc 9-1)."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pyyq.errors import UnknownFormatError
from pyyq.options import Options


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

    def from_filename(self, filename: str) -> FormatSpec:
        """Guess from the extension; unknown extensions default to yaml (Go behaviour)."""
        if filename:
            ext = os.path.splitext(filename)[1]
            if len(ext) >= 2 and ext.startswith("."):
                name = ext[1:].lower()
                for spec in self._specs:
                    if spec.matches(name) or name in [e.lstrip(".") for e in spec.extensions]:
                        return spec
        return self.get("yaml")

    def input_formats(self) -> list[str]:
        return [s.name for s in self._specs if s.decoder_factory is not None]

    def output_formats(self) -> list[str]:
        return [s.name for s in self._specs if s.encoder_factory is not None]

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
        from pyyq.formats.json_codec import JsonDecoder, JsonEncoder
        from pyyq.formats.props_codec import PropertiesEncoder
        from pyyq.formats.toon_codec import ToonEncoder
        from pyyq.formats.yaml.codec import YamlDecoder, YamlEncoder

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
            decoder_factory=None,
            encoder_factory=lambda o, u: PropertiesEncoder(o, unwrap_scalar=u),
            unwrap_scalar_default=True,
        ))
        reg.register(FormatSpec(
            "toon", (), (".toon",),
            decoder_factory=None,
            encoder_factory=lambda o, u: ToonEncoder(o, unwrap_scalar=u),
            unwrap_scalar_default=False,
        ))
        _builtin = reg.freeze()
    return _builtin
