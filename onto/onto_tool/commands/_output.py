import sys


def warn(messages: list[str]) -> None:
    for message in messages:
        print(f"주의: {message}", file=sys.stderr)
