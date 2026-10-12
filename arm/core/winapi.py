"""Thin ctypes wrapper around the Win32 APIs used to drive optical drives.

Everything here degrades gracefully on non-Windows systems so the rest of the
application (and the test-suite) can run on Linux/macOS. For development a
fake drive can be simulated with the ``ARM_SIM_DRIVE`` environment variable
(see :mod:`arm.core.drives`).
"""
from __future__ import annotations

import ctypes
import os
import string
import sys
from dataclasses import dataclass

IS_WINDOWS = sys.platform == "win32"

# Drive types (GetDriveTypeW)
DRIVE_CDROM = 5

# Error modes
SEM_FAILCRITICALERRORS = 0x0001
SEM_NOOPENFILEERRORBOX = 0x8000

# CreateFile
GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

# IOCTLs
IOCTL_STORAGE_CHECK_VERIFY2 = 0x002D0800
IOCTL_STORAGE_EJECT_MEDIA = 0x002D4808
IOCTL_STORAGE_LOAD_MEDIA = 0x002D480C
IOCTL_STORAGE_MEDIA_REMOVAL = 0x002D4804
IOCTL_CDROM_READ_TOC = 0x00024000


@dataclass
class TocTrack:
    number: int
    is_data: bool
    lba: int


if IS_WINDOWS:
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _k32.GetLogicalDrives.restype = wintypes.DWORD
    _k32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    _k32.GetDriveTypeW.restype = wintypes.UINT
    _k32.SetErrorMode.argtypes = [wintypes.UINT]
    _k32.SetErrorMode.restype = wintypes.UINT
    _k32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    _k32.CreateFileW.restype = wintypes.HANDLE
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.CloseHandle.restype = wintypes.BOOL
    _k32.DeviceIoControl.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
        wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID,
    ]
    _k32.DeviceIoControl.restype = wintypes.BOOL
    _k32.GetVolumeInformationW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD,
    ]
    _k32.GetVolumeInformationW.restype = wintypes.BOOL


def suppress_error_dialogs() -> None:
    """Prevent Windows from showing 'There is no disk in the drive' popups."""
    if IS_WINDOWS:
        _k32.SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOOPENFILEERRORBOX)


def list_optical_drives() -> list[str]:
    """Return the drive letters (e.g. ``['D:', 'E:']``) of every optical drive."""
    if not IS_WINDOWS:
        return []
    mask = _k32.GetLogicalDrives()
    drives = []
    for i, letter in enumerate(string.ascii_uppercase):
        if mask & (1 << i) and _k32.GetDriveTypeW(f"{letter}:\\") == DRIVE_CDROM:
            drives.append(f"{letter}:")
    return drives


def _open_device(drive: str):
    letter = drive.rstrip(":\\/")
    path = "\\\\.\\" + letter + ":"
    handle = _k32.CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                              None, OPEN_EXISTING, 0, None)
    if handle in (None, INVALID_HANDLE_VALUE):
        return None
    return handle


def _ioctl(handle, code: int, in_buf=None, out_buf=None) -> bool:
    returned = wintypes.DWORD(0)
    in_ptr = ctypes.byref(in_buf) if in_buf is not None else None
    in_len = ctypes.sizeof(in_buf) if in_buf is not None else 0
    out_ptr = ctypes.byref(out_buf) if out_buf is not None else None
    out_len = ctypes.sizeof(out_buf) if out_buf is not None else 0
    return bool(_k32.DeviceIoControl(handle, code, in_ptr, in_len, out_ptr, out_len,
                                     ctypes.byref(returned), None))


def media_present(drive: str) -> bool:
    """True if a disc is loaded and the drive reports it ready."""
    if not IS_WINDOWS:
        return False
    handle = _open_device(drive)
    if handle is None:
        return False
    try:
        return _ioctl(handle, IOCTL_STORAGE_CHECK_VERIFY2)
    finally:
        _k32.CloseHandle(handle)


def read_toc(drive: str) -> list[TocTrack] | None:
    """Read the disc table of contents. Returns ``None`` if it can't be read."""
    if not IS_WINDOWS:
        return None

    class TRACK_DATA(ctypes.Structure):
        _fields_ = [("Reserved", ctypes.c_ubyte), ("CtrlAdr", ctypes.c_ubyte),
                    ("TrackNumber", ctypes.c_ubyte), ("Reserved1", ctypes.c_ubyte),
                    ("Address", ctypes.c_ubyte * 4)]

    class CDROM_TOC(ctypes.Structure):
        _fields_ = [("Length", ctypes.c_ubyte * 2), ("FirstTrack", ctypes.c_ubyte),
                    ("LastTrack", ctypes.c_ubyte), ("TrackData", TRACK_DATA * 100)]

    handle = _open_device(drive)
    if handle is None:
        return None
    try:
        toc = CDROM_TOC()
        if not _ioctl(handle, IOCTL_CDROM_READ_TOC, out_buf=toc):
            return None
        tracks = []
        count = toc.LastTrack - toc.FirstTrack + 1
        for i in range(max(0, min(count, 99))):
            td = toc.TrackData[i]
            control = td.CtrlAdr & 0x0F  # MSVC bitfield: Control is the low nibble
            m, s, f = td.Address[1], td.Address[2], td.Address[3]
            lba = (m * 60 + s) * 75 + f - 150
            tracks.append(TocTrack(td.TrackNumber, bool(control & 0x04), lba))
        return tracks
    finally:
        _k32.CloseHandle(handle)


def volume_label(drive: str) -> str:
    if not IS_WINDOWS:
        return ""
    buf = ctypes.create_unicode_buffer(261)
    fs = ctypes.create_unicode_buffer(261)
    ok = _k32.GetVolumeInformationW(f"{drive}\\", buf, 261, None, None, None, fs, 261)
    return buf.value if ok else ""


def eject(drive: str) -> bool:
    if not IS_WINDOWS:
        return False
    handle = _open_device(drive)
    if handle is None:
        return False
    try:
        class PREVENT_MEDIA_REMOVAL(ctypes.Structure):
            _fields_ = [("PreventMediaRemoval", ctypes.c_ubyte)]
        _ioctl(handle, IOCTL_STORAGE_MEDIA_REMOVAL, in_buf=PREVENT_MEDIA_REMOVAL(0))
        return _ioctl(handle, IOCTL_STORAGE_EJECT_MEDIA)
    finally:
        _k32.CloseHandle(handle)


def close_tray(drive: str) -> bool:
    if not IS_WINDOWS:
        return False
    handle = _open_device(drive)
    if handle is None:
        return False
    try:
        return _ioctl(handle, IOCTL_STORAGE_LOAD_MEDIA)
    finally:
        _k32.CloseHandle(handle)


def running_process_names() -> set[str]:
    """Lower-case names of running processes (used to check XReveal is alive)."""
    names: set[str] = set()
    if IS_WINDOWS:
        import subprocess
        try:
            out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True,
                                 text=True, timeout=10,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        except (OSError, subprocess.SubprocessError):
            return names
        for line in out.splitlines():
            if line.startswith('"'):
                names.add(line.split('","', 1)[0].strip('"').lower())
    else:
        for pid in os.listdir("/proc") if os.path.isdir("/proc") else []:
            try:
                with open(f"/proc/{pid}/comm") as fh:
                    names.add(fh.read().strip().lower())
            except OSError:
                pass
    return names
