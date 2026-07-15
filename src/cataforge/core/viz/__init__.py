"""Visualisation intermediate representation (IR) + text renderers.

Pure, standard-library-only. Collectors (``application.viz``) map data
sources onto the three closed IR forms here; renderers turn an IR into a
text format. Keeping both in ``core`` lets ``application`` and ``interface``
call-sites share one renderer without an upward import.
"""

from __future__ import annotations
