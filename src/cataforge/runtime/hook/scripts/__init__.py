"""Built-in hook scripts — invoked via the deploying interpreter as
``"<sys.executable>" -m cataforge.runtime.hook.scripts.<name>``."""

from cataforge.utils.encoding import ensure_utf8

# Hook processes are their own entry-point boundary: the IDE invokes them
# directly, so no CLI entry point has put them in UTF-8 mode. Without this,
# a non-UTF-8 locale mis-decodes profile.yaml / hooks.yaml and tool-name
# matching silently falls back to defaults.
ensure_utf8()
