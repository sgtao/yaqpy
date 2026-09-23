**English** | [日本語](https://github.com/sgtao/yaqpy/blob/main/README.ja.md)

<p align="center">
  <img src="https://raw.githubusercontent.com/sgtao/yaqpy/main/logo.svg" alt="yaqpy — YAML and more, Query editor in Python" width="600">
</p>

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/sgtao/yaqpy/blob/main/LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/downloads/)
[![GitHub release](https://img.shields.io/github/v/release/sgtao/yaqpy.svg)](https://github.com/sgtao/yaqpy/releases)

# yaqpy — YAML and more, Query editor in Python

A lightweight tool to **query, update and convert** YAML, JSON and more with expressions, from the command line or from Python.

- It follows the expression language of the popular CLI tool [mikefarah/yq](https://github.com/mikefarah/yq) (Go, v4.53.6)
- It is re-implemented with **nothing but the Python standard library**
- The name stands for **Y**AML **A**nd more, **Q**uery editor in **PY**thon

```console
$ yaqpy '.server.port' config.yaml
8080
$ yaqpy -i '.server.port = 9090' config.yaml     # comments and key order are kept
```

## Features

- **Keeps your formatting**: comments, key order, anchors (`&` / `*`) and the way numbers and quotes were written (`0x1F`, `1.50`, `'yes'`) survive an update
- **No dependencies**: all it needs is Python 3.13 or later. The GUI is an optional extra (Flet); the web version adds flet-web
- **Four ways to use it**: the `yaqpy` command, the Python library (`import yaqpy`), a desktop GUI (`yaqpy-gui`) and the same GUI in a web browser (`yaqpy-web`)
- **Formats**: YAML, JSON, XML, CSV / TSV, TOML, properties and TOON (a token-saving format for LLMs), both in and out. TOML comments are not kept, so `-i` on TOML is refused by default
- **Compatible with yq**: 1,091 test scenarios of the Go version are run as compatibility tests (1,047 of the 1,051 comparable ones match). Every operator works except `load` and friends, `eval`, `envsubst`, `system` and `error`
- **Beyond yq** (not in the Go version):
  - the input format is detected from the content when the file extension does not tell it
  - `yaqpy --schema data.yaml` prints a JSON Schema (Draft 2020-12) of the data, as JSON or YAML
  - `yaqpy --recipe openai-to-gemini request.json` converts request bodies between OpenAI, Gemini and Anthropic, and reports what was dropped, added, or does not fit the target schema (results go to stdout; files are written only with `--apply --out-dir`; no API is called)
  - yaqpy describes itself for people and AI: `--print-spec` (the operators that work and those that do not), `--example`, `--guide-prompt` (a prompt that lets an AI write yaqpy expressions) and `--skill-md` (a Claude Code skill)
- **GUI extras**: an "Ask AI" tab that builds a prompt for an AI to write your expression; expressions saved and loaded as `.yaqpy` files (the command reads them too: `yaqpy sample.yaqpy data.json`); a run log with a Log tab to browse, search and re-run past conversions (desktop only); file drag-and-drop in the web version
- **Safe defaults**: as a library, operators that read files or environment variables or run commands are all off. The CLI, like the Go version, allows environment variables and file reads (commands stay off). The web version always turns them off

## Installation

Python 3.13 or later is required.

```bash
pip install yaqpy                   # the yaqpy command and the library (no dependencies)
pip install "yaqpy[gui]"            # + the desktop GUI (adds Flet)
pip install "yaqpy[web]"            # + the GUI in a web browser (adds Flet and flet-web)
```

With [uv](https://docs.astral.sh/uv/):

```bash
uv tool install yaqpy               # install the yaqpy command
uv tool install "yaqpy[gui,web]" --with flet-desktop  # ... with what yaqpy-gui and yaqpy-web need
uvx yaqpy '.server.port' config.yaml   # run it once without installing
uv add yaqpy                        # use it as a library in a uv project
```

> **`uv tool install` / `uvx` and the desktop GUI**: `flet` normally installs its desktop runtime (`flet-desktop`) on first launch. That auto-install targets whatever virtual environment `uv` can find near the current directory, which is **not** the isolated environment `uv tool install` created for `yaqpy` — so it can print "OK" and still leave you with `ModuleNotFoundError: No module named 'flet_desktop'` when you run `yaqpy-gui`. Passing `--with flet-desktop` (as above) puts it in the right place from the start and avoids this entirely. If you already installed without it: `uv tool install --force "yaqpy[gui]" --with flet-desktop`.

**From GitHub Releases** (for example, a version that is not on PyPI): pick a version on [Releases](https://github.com/sgtao/yaqpy/releases) and replace `0.7.0` / `v0.7.0` below with it.

```bash
pip install "yaqpy[gui] @ https://github.com/sgtao/yaqpy/releases/download/v0.7.0/yaqpy-0.7.0-py3-none-any.whl"
pip install "yaqpy[gui] @ git+https://github.com/sgtao/yaqpy@v0.7.0"
```

To work on the source, see [DEVELOPMENT.md](https://github.com/sgtao/yaqpy/blob/main/DEVELOPMENT.md) (Japanese).

## Quick start

Take this `config.yaml`:

```yaml
# server settings
server:
  port: 8080 # dev
  hosts: [a, b]
items:
  - {name: pen, price: 120}
  - {name: book, price: 980}
```

**Command line**

```bash
yaqpy '.server.port' config.yaml                              # read -> 8080
yaqpy '.items[] | select(.price > 500) | .name' config.yaml   # filter -> book
yaqpy -i '.server.port = 9090' config.yaml                    # update (comments and key order are kept)
yaqpy -o json '.server' config.yaml                           # convert (yaml / json / xml / csv / tsv / toml / props / toon)
```

**Python library**

```python
import yaqpy

yaqpy.evaluate(".server.port", "server:\n  port: 8080\n")        # '8080\n'
yaqpy.query(".items[] | select(.price > 500)", {"items": [{"price": 1}, {"price": 900}]})   # [{'price': 900}]
yaqpy.update(".server.port = 9090", {"server": {"port": 8080}})  # {'server': {'port': 9090}}
```

**GUI**

```bash
yaqpy-gui                # desktop window (or: yaqpy --gui)
yaqpy-web                # the same screens in your browser at http://127.0.0.1:8550/ (or: yaqpy --web)
yaqpy-web --port 9000    # another port; see yaqpy-web --help for the options
```

The web version listens on this PC only by default and has no authentication. Files are uploaded from the browser and results come back as downloads.

## Documentation

The detailed guides are written in **Japanese**.

| Contents | File |
|---|---|
| This README in Japanese | [README.ja.md](https://github.com/sgtao/yaqpy/blob/main/README.ja.md) |
| The command, each format, JSON Schema output, recipes, the library, the operators, and the differences from Go yq | [USAGE.ja.md](https://github.com/sgtao/yaqpy/blob/main/USAGE.ja.md) |
| The GUI (desktop and web) | [USAGE-GUI.ja.md](https://github.com/sgtao/yaqpy/blob/main/USAGE-GUI.ja.md) |
| For developers (setup, design, tests, repository layout) | [DEVELOPMENT.md](https://github.com/sgtao/yaqpy/blob/main/DEVELOPMENT.md) |
| Changes in each version (features, known limitations) | [CHANGELOG.md](https://github.com/sgtao/yaqpy/blob/main/CHANGELOG.md) |

`yaqpy --help`, `yaqpy-gui --help` and `yaqpy-web --help` are in English.

## License

[MIT License](https://github.com/sgtao/yaqpy/blob/main/LICENSE)

The design and the test scenarios draw on Go yq (MIT); see [NOTICE](https://github.com/sgtao/yaqpy/blob/main/NOTICE).

---

🤖 Built with [Claude Code](https://claude.com/claude-code)
