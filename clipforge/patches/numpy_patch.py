"""
Patch: NumPy ABI / deprecation shims
-------------------------------------
Newer NumPy (≥1.24) removed several long-deprecated aliases
(``np.float``, ``np.int``, ``np.object``, ``np.bool``, etc.) that older
builds of torch / torchaudio / pyannote still reference at import time.

We restore the aliases *before* those libraries are imported so they
never see an ``AttributeError``.

Also silences the ``np.ComplexWarning`` rename in NumPy 2.x.
"""
from __future__ import annotations

import warnings


def patch() -> None:
    # ---- silence numpy deprecation / future warnings globally ----------
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="numpy")
    warnings.filterwarnings("ignore", category=FutureWarning, module="numpy")
    warnings.filterwarnings("ignore", category=FutureWarning, message=".*np\\..*")

    try:
        import numpy as np
    except ImportError:
        return  # numpy not installed yet – nothing to patch

    _ALIASES = {
        "float": float,
        "int": int,
        "object": object,
        "bool": bool,
        "complex": complex,
        "str": str,
        "long": int,
        "unicode": str,
    }
    for name, builtin in _ALIASES.items():
        try:
            getattr(np, name)
        except (AttributeError, FutureWarning):
            setattr(np, name, builtin)

    # NumPy 2.x renamed ComplexWarning → exceptions.ComplexWarning
    if not hasattr(np, "ComplexWarning"):
        try:
            from numpy.exceptions import ComplexWarning
            np.ComplexWarning = ComplexWarning  # type: ignore[attr-defined]
        except (ImportError, AttributeError):
            pass
