"""Utilidad de memoria: devolver al SISTEMA OPERATIVO la memoria liberada.

En Linux con glibc (Render), cuando pandas/numpy liberan DataFrames grandes tras un
trabajo pesado (escaneo del screener, backtest del universo), Python marca esos bloques
como libres PERO glibc los retiene en su "arena" y NO los devuelve al SO. La RSS que mide
Render se queda en el máximo alcanzado (efecto "escalón" que trepa hacia el límite de
512MB). `malloc_trim(0)` fuerza a glibc a devolver esa memoria libre al SO, bajando la RSS.

Uso: llamar `mem.trim()` justo después de un job que crea y descarta muchos DataFrames.
Es best-effort y barato; si no hay libc/malloc_trim (no glibc), solo hace gc.collect().
"""
import ctypes
import ctypes.util
import gc
import logging

logger = logging.getLogger("mem")

_libc = None
try:
    _name = ctypes.util.find_library("c") or "libc.so.6"
    _libc = ctypes.CDLL(_name)
    if not hasattr(_libc, "malloc_trim"):
        _libc = None
except Exception:
    _libc = None


def trim() -> None:
    """gc.collect() + devolver la memoria libre de glibc al SO (best-effort)."""
    try:
        gc.collect()
    except Exception:
        pass
    if _libc is not None:
        try:
            _libc.malloc_trim(0)
        except Exception:
            pass
