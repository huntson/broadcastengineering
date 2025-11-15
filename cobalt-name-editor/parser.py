# cobalt-name-editor/parser.py
import re

# device-line pattern:
#   optional leading WS   device <nr>  whitespace  "name"  rest-of-line
LINE_RE = re.compile(
    r'^[ \t]*(device)\s+(\d+)\s+"([^"]+)"(.*)$',
    re.I | re.MULTILINE,
)

def extract_names(text: str) -> list[str]:
    """Return the names in order from the file."""
    return [m.group(3) for m in LINE_RE.finditer(text)]

def rebuild_file(original: str, new_names: list[str]) -> str:
    """
    Replace the first *len(new_names)* device-name lines.
    Abort (ValueError) if we can't find enough lines.
    """
    out, idx = [], 0

    for line in original.splitlines():
        m = LINE_RE.match(line)
        if m and idx < len(new_names):
            # build the replacement line keeping the original spacing & tail
            out.append(f'{m.group(1)} {m.group(2)} "{new_names[idx]}"{m.group(4)}')
            idx += 1
        elif m and idx >= len(new_names):
            # we've renamed all we were given → DROP any extra template lines
            continue
        else:
            out.append(line)

    if idx < len(new_names):
        raise ValueError(
            f"Only found {idx} device lines; expected at least {len(new_names)}."
        )

    return "\n".join(out)
