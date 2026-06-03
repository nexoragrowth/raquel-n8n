"""
Helper para cargar credenciales desde .env del repo.
Uso:
    from lib_env import env
    api_key = env('N8N_API_KEY')
"""
import os
from pathlib import Path

_loaded = False
_cache = {}


def _load():
    global _loaded
    if _loaded:
        return
    # Buscar .env desde el cwd hacia arriba
    here = Path(__file__).resolve().parent
    for d in [here.parent, here, Path.cwd()]:
        envf = d / ".env"
        if envf.exists():
            for line in envf.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                _cache[k] = v
            break
    _loaded = True


def env(name, default=None):
    """Devuelve var de entorno, fallback a .env del repo, fallback a default."""
    _load()
    return os.environ.get(name) or _cache.get(name) or default


def require(name):
    """Devuelve var o termina con error claro."""
    v = env(name)
    if not v:
        import sys
        sys.exit(f"ERROR: missing env var {name} (set in environment or .env)")
    return v
