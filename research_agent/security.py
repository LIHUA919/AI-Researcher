from __future__ import annotations

from collections.abc import Mapping
import re


SENSITIVE_ENVIRONMENT_NAME_PARTS = (
    "KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "CREDENTIAL",
    "AUTHORIZATION",
)
_AUTHORIZATION_HEADER = re.compile(
    r"(?im)(\bauthorization\s*:\s*)[^\r\n]+"
)


def redact_sensitive_environment_values(
    output: str,
    environment: Mapping[str, str],
    *,
    replacement_template: str = "<redacted:{name}>",
) -> str:
    sensitive_values = sorted(
        (
            (value, name)
            for name, value in environment.items()
            if value
            and any(
                part in name.upper()
                for part in SENSITIVE_ENVIRONMENT_NAME_PARTS
            )
        ),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
    for value, name in sensitive_values:
        replacement = replacement_template.replace("{name}", name)
        output = output.replace(value, replacement)
    header_replacement = replacement_template.replace(
        "{name}",
        "Authorization",
    )
    return _AUTHORIZATION_HEADER.sub(
        lambda match: f"{match.group(1)}{header_replacement}",
        output,
    )
