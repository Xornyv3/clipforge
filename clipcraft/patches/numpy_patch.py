"""Fix numpy attribute deprecations that break older numba and librosa versions.

NumPy >= 1.24 removed aliases like np.float, np.int, np.complex, etc.
Older versions of numba and librosa still reference these, causing
AttributeError at import time.  This patch restores them silently.
"""

import sys


def apply():
    """Restore removed numpy aliases so legacy libraries keep working."""
    try:
        import numpy as np
    except ImportError:
        return

    import builtins

    # Restore type aliases removed in numpy 1.24+
    _aliases = {
        "float": builtins.float,
        "int": builtins.int,
        "complex": builtins.complex,
        "object": builtins.object,
        "bool": builtins.bool,
        "str": builtins.str,
    }
    for name, fallback in _aliases.items():
        if not hasattr(np, name):
            setattr(np, name, fallback)

    # numpy.warnings was removed; some old code still references it
    if not hasattr(np, "warnings"):
        import warnings
        np.warnings = warnings

    # Silence numpy deprecation chatter
    try:
        import warnings
        warnings.filterwarnings("ignore", category=DeprecationWarning, module="numpy")
    except Exception:
        pass
