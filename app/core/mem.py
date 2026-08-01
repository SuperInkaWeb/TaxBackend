"""Lectura del RSS (memoria residente) del proceso actual.

Linux (producción) vía /proc; Windows (local) vía WinAPI. Devuelve MB o None.
"""


def rss_mb() -> float | None:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)  # KB → MB
    except OSError:
        pass
    try:
        import ctypes
        import ctypes.wintypes as wt

        class _PMC(ctypes.Structure):
            _fields_ = [
                ("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ]
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        p = ctypes.WinDLL("psapi", use_last_error=True)
        k.GetCurrentProcess.restype = wt.HANDLE
        p.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(_PMC), wt.DWORD]
        pmc = _PMC(); pmc.cb = ctypes.sizeof(_PMC)
        p.GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
        return round(pmc.WorkingSetSize / 1024 / 1024, 1)
    except Exception:
        return None
