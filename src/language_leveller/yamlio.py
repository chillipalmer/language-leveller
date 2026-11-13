"""YAML loading for config and grammar files.

PyYAML follows YAML 1.1, where bare yes/no/on/off become booleans. In a grammar
file those are real words (Spanish "no", English "on"), so only `true`/`false`
are treated as booleans here.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


class _Loader(yaml.SafeLoader):
    pass


_Loader.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in v if tag != "tag:yaml.org,2002:bool"]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"))


def load(path: str | Path):
    return yaml.load(Path(path).read_text(encoding="utf-8"), Loader=_Loader)


def loads(text: str):
    return yaml.load(text, Loader=_Loader)
