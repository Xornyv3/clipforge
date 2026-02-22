"""Apply all startup compatibility patches before other imports.

Importing this package is enough — patches run at import time.
"""

from . import numpy_patch
from . import whisper_patch

numpy_patch.apply()
whisper_patch.apply()
