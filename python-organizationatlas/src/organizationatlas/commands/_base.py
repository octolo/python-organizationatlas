"""Factory for organizationatlas CLI commands."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from clicommands.commands.args import parse_args_from_config
from clicommands.commands.base import Command
from clicommands.utils import print_header, print_separator
from providerkit.commands.provider import _PROVIDER_COMMAND_CONFIG


def make_command(
    helper: Callable[..., Any],
    api_command: str,
    arg_name: str,
    description: str,
    with_readable: bool = False,
) -> Command:
    """Build a CLI Command that calls helper and prints provider results."""
    arg_config = {
        **_PROVIDER_COMMAND_CONFIG,
        arg_name: {"type": str, "default": ""},
    }
    if with_readable:
        arg_config["readable"] = {"type": "store_true"}

    prog = api_command.replace("_", "-")

    def _run(args: list[str]) -> bool:
        parsed = parse_args_from_config(args, arg_config, prog=prog)
        kwargs: dict[str, Any] = {}
        attr_value = parsed.get("attr", {})
        if isinstance(attr_value, dict):
            kwargs["attribute_search"] = attr_value.get("kwargs", {})
        output_format = parsed.get("format", "terminal")
        raw = parsed.get("raw", False)
        arg_value = parsed.pop(arg_name)
        first = parsed.pop("first", False)
        readable = parsed.get("readable", False) if with_readable else False

        results = helper(arg_value, first=first, **kwargs)
        for pv in results:
            name = pv["provider"].name
            elapsed = pv["response_time"]
            print_separator()
            print_header(f"{name} - {elapsed}s")
            print_separator()
            response_kwargs = {"readable": readable} if with_readable else {}
            print(pv["provider"].response(api_command, raw, output_format, **response_kwargs))
        return True

    return Command(_run, description)
