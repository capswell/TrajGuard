"""Best-effort process peak RSS (not aggregate memory of a process pool)."""
import sys


def peak_rss_bytes():
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            class Counters(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
            result = Counters()
            result.cb = ctypes.sizeof(result)
            if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(result), result.cb):
                return None
            return int(result.PeakWorkingSetSize)
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(peak if sys.platform == "darwin" else peak*1024)
    except (ImportError, OSError, AttributeError):
        return None
