# Custom hooks

Drop your own hook scripts here and reference them from `hooks.yaml` with
the `custom:` prefix:

```yaml
hooks:
  PreToolUse:
    - script: custom:my_scan
      matcher_capability: shell_exec
      type: block
      description: "Run internal policy scanner before shell commands"
```

`cataforge deploy` will wire the hook into the platform's config so that
the IDE invokes `python .cataforge/hooks/custom/my_scan.py` with the
standard hook JSON payload on stdin.

## Contract

* **stdin**: JSON payload (`tool_name`, `tool_input`, etc.) — same shape
  as built-in hooks.
* **stdout / stderr**: free text; the IDE surfaces stderr on block.
* **exit code**:
  * `0` = allow / observation recorded
  * `2` = block the tool call (only honoured for `type: block` hooks)
  * anything else = block with a generic error

## Minimum example

```python
# .cataforge/hooks/custom/my_scan.py
import sys

from cataforge.hook.base import read_hook_input

payload = read_hook_input()
cmd = (payload.get("tool_input") or {}).get("command", "")

if "aws ec2 terminate-instances" in cmd:
    print("BLOCKED: use the wrapper script instead", file=sys.stderr)
    sys.exit(2)

sys.exit(0)
```

> Always use `read_hook_input()` (or `cataforge.core.io.read_stdin_utf8()`)
> instead of `sys.stdin.read()` — Python's text-mode stdin decodes through
> the platform locale (cp936 on Chinese Windows, cp1252 on Western Windows),
> which corrupts UTF-8 payloads.

## Re-use the shared helpers

To share behaviour with built-in hooks (`matches_capability`, stdin
parsing, error logging), import from `cataforge.hook.base`:

```python
from cataforge.hook.base import matches_capability, read_hook_input
```
