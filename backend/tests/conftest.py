"""Pytest scaffolding.

让 backend/ 作为 import root，使 `from services.xxx import ...` 这样的导入在测试里可用。
"""
import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# 给 SETTINGS_PATH 一个测试专用临时根，避免污染用户的真实 settings.json
os.environ.setdefault("APPDATA", str(_BACKEND_DIR / ".test-tmp"))
