"""Fix conflicts between OpenAI Whisper, PyTorch, and Triton.

- Triton does not support Windows; suppress its import errors.
- Newer PyTorch emits FutureWarning for torch.load without weights_only;
  patch it so Whisper model loading stays quiet.
- Mute verbose Whisper progress bars when not wanted.
"""

import os
import sys


def apply():
    """Apply Whisper / PyTorch compatibility patches."""

    # ---------- Triton on Windows ----------
    if sys.platform == "win32":
        # Triton wheels don't ship for Windows; prevent noisy ImportError
        os.environ.setdefault("TRITON_PTXAS_PATH", "")
        os.environ.setdefault("NO_TORCH_DYNAMO", "1")

    # ---------- Suppress Whisper verbose output ----------
    os.environ.setdefault("WHISPER_VERBOSE", "0")

    # ---------- Patch torch.load for weights_only default ----------
    try:
        import torch

        _original_load = torch.load

        def _patched_load(*args, **kwargs):
            if "weights_only" not in kwargs:
                kwargs["weights_only"] = False
            return _original_load(*args, **kwargs)

        torch.load = _patched_load
    except ImportError:
        pass
    except Exception:
        pass

    # ---------- Suppress common FutureWarning noise ----------
    try:
        import warnings
        warnings.filterwarnings("ignore", category=FutureWarning, module="torch")
        warnings.filterwarnings("ignore", category=UserWarning, module="whisper")
    except Exception:
        pass
