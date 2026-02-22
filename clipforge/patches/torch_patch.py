"""
Patch: PyTorch / torchaudio compatibility
------------------------------------------
* Pins ``torch.classes`` to avoid ``AttributeError`` in older torchvision
  builds that probe ``torch.classes.__path__``.
* Adds a no-op ``torch.compiler`` stub so code written for PyTorch ≥2.1
  doesn't crash on 2.0.x installs.
* Ensures ``torchaudio.functional`` is importable even when the backend
  hasn't been set yet (needed by pyannote.audio).
"""
from __future__ import annotations

import importlib
import sys
import types
import warnings


def patch() -> None:
    warnings.filterwarnings("ignore", message=".*torch.*", category=UserWarning)
    warnings.filterwarnings("ignore", message=".*pynvml.*", category=FutureWarning)

    # ---------- torch.classes stub ----------
    if "torch" not in sys.modules:
        # If torch hasn't been imported yet we create a lightweight shim
        # so anything checking ``torch.classes`` won't blow up during
        # module-level attribute probes.
        _dummy = types.ModuleType("torch.classes")
        _dummy.__path__ = []  # type: ignore[attr-defined]
        sys.modules.setdefault("torch.classes", _dummy)

    # ---------- torch.compiler stub (PyTorch <2.1) ----------
    if "torch.compiler" not in sys.modules:
        _compiler = types.ModuleType("torch.compiler")
        _compiler.is_compiling = lambda: False  # type: ignore[attr-defined]
        _compiler.disable = lambda fn=None, **kw: fn if fn else (lambda f: f)  # type: ignore[attr-defined]
        sys.modules["torch.compiler"] = _compiler

    # ---------- torchaudio backend shim ----------
    try:
        import torchaudio  # noqa: F401
    except Exception:
        pass  # torchaudio not installed – skip

    try:
        if "torchaudio" in sys.modules:
            ta = sys.modules["torchaudio"]
            # Ensure the sox/soundfile backend is registered silently
            if hasattr(ta, "set_audio_backend"):
                try:
                    ta.set_audio_backend("soundfile")
                except Exception:
                    try:
                        ta.set_audio_backend("sox_io")
                    except Exception:
                        pass
    except Exception:
        pass
