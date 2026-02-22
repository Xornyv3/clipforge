"""
Patch: Whisper / faster-whisper compatibility
----------------------------------------------
* Monkey-patches ``whisper.load_model`` to accept the ``device`` keyword
  even on older builds that only took positional args.
* Silences the ``FP16 is not supported on CPU`` warning that appears when
  running on a machine without a CUDA GPU.
* Ensures ``faster_whisper`` can find the CTranslate2 shared libs when
  they live in a non-standard location (common in conda envs).
"""
from __future__ import annotations

import os
import sys
import warnings


def patch() -> None:
    warnings.filterwarnings("ignore", message=".*FP16 is not supported on CPU.*")
    warnings.filterwarnings("ignore", message=".*Whisper.*", category=UserWarning)

    # ---- faster-whisper CT2 library path ----
    ct2_lib = os.environ.get("CT2_LIB_PATH")
    if ct2_lib and os.path.isdir(ct2_lib):
        if sys.platform == "win32":
            os.add_dll_directory(ct2_lib)
        else:
            ld = os.environ.get("LD_LIBRARY_PATH", "")
            if ct2_lib not in ld:
                os.environ["LD_LIBRARY_PATH"] = f"{ct2_lib}:{ld}"

    # ---- whisper load_model wrapper (guard against missing 'device' kwarg) ----
    try:
        import whisper as _whisper  # noqa: F811

        _orig_load = getattr(_whisper, "load_model", None)
        if _orig_load is not None:
            import functools
            import inspect

            sig = inspect.signature(_orig_load)
            if "device" not in sig.parameters:
                @functools.wraps(_orig_load)
                def _patched_load(*args, **kwargs):
                    kwargs.pop("device", None)
                    return _orig_load(*args, **kwargs)

                _whisper.load_model = _patched_load  # type: ignore[attr-defined]
    except ImportError:
        pass
