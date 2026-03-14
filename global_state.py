"""Global runtime state flags shared across modules.

These flags coordinate initialization and lifecycle across the web UI,
CLI entry points, and the research agent pipeline.
"""

LOG_PATH = ""

START_FLAG = False
FIRST_MAIN = False

EXIT_FLAG = False
INIT_FLAG = False
