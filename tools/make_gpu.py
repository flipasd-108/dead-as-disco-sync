"""Release step: python tools/make_gpu.py disco_sync.py -> disco_sync_gpu.py: same code, torch and torchaudio from the PyTorch CUDA 12.6 index."""
from pathlib import Path
import sys
src = Path(sys.argv[1]); s = src.read_text(encoding="utf-8")
header = '''# ]
# [[tool.uv.index]]
# name = "pytorch-cu126"
# url = "https://download.pytorch.org/whl/cu126"
# explicit = true
# [tool.uv.sources]
# torch = { index = "pytorch-cu126" }
# torchaudio = { index = "pytorch-cu126" }
'''
assert s.count("\n# ]\n") == 1
src.with_name("disco_sync_gpu.py").write_text(s.replace("\n# ]\n", "\n" + header, 1), encoding="utf-8")
