# ClipForge – AI-powered podcast/interview clip extractor
# -------------------------------------------------------
# This package is imported *after* the startup patches have already been
# applied by the CLI entry-point (run.py).  Do NOT import heavy ML libs
# at the top level of any sub-module; lazy-import inside functions instead.

__version__ = "1.0.0"
