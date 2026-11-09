import sys
from pathlib import Path

# Compatibilidad para ejecucion standalone (ej. Render) o como subdirectorio
_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))
if str(_backend_root.parent) not in sys.path:
    sys.path.insert(0, str(_backend_root.parent))

# Alias para que 'from backend.app...' funcione cuando la raiz es el repo backend
if "backend" not in sys.modules:
    import types
    _backend_mod = types.ModuleType("backend")
    _backend_mod.__path__ = [str(_backend_root)]
    sys.modules["backend"] = _backend_mod
