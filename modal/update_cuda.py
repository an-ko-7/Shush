import os

os.environ.setdefault("MODAL_IMAGE_BUILDER_VERSION", "2025.06")

# Re-export the app so `modal deploy update_cuda.py` rebuilds the image
# with the latest CUDA base set in shush.py.
from shush import app  # noqa: F401
