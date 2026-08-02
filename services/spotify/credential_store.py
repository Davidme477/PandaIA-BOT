from __future__ import annotations

from ctypes import POINTER, Structure, byref, c_byte, c_void_p, cast, windll
from ctypes import wintypes
import sys


SPOTIFY_CREDENTIAL_TARGET = "PandaIA BOT/Spotify OAuth"


class CredentialStoreError(RuntimeError):
    pass


class _Credential(Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", POINTER(c_byte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


class WindowsCredentialStore:
    """Almacena el refresh token mediante Windows Credential Manager."""

    def __init__(self, target: str = SPOTIFY_CREDENTIAL_TARGET) -> None:
        if sys.platform != "win32":
            raise CredentialStoreError("El Administrador de credenciales requiere Windows.")
        self.target = target
        self._advapi = windll.advapi32
        self._advapi.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, POINTER(POINTER(_Credential))]
        self._advapi.CredReadW.restype = wintypes.BOOL
        self._advapi.CredWriteW.argtypes = [POINTER(_Credential), wintypes.DWORD]
        self._advapi.CredWriteW.restype = wintypes.BOOL
        self._advapi.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self._advapi.CredDeleteW.restype = wintypes.BOOL
        self._advapi.CredFree.argtypes = [c_void_p]

    def get(self) -> str:
        pointer = POINTER(_Credential)()
        if not self._advapi.CredReadW(self.target, 1, 0, byref(pointer)):
            return ""
        try:
            credential = pointer.contents
            if not credential.CredentialBlob or not credential.CredentialBlobSize:
                return ""
            raw = bytes(
                cast(credential.CredentialBlob, POINTER(c_byte * credential.CredentialBlobSize)).contents
            )
            return raw.decode("utf-8")
        finally:
            self._advapi.CredFree(pointer)

    def set(self, value: str) -> None:
        raw = value.strip().encode("utf-8")
        if not raw:
            self.clear()
            return
        blob = (c_byte * len(raw)).from_buffer_copy(raw)
        credential = _Credential()
        credential.Type = 1
        credential.TargetName = self.target
        credential.CredentialBlobSize = len(raw)
        credential.CredentialBlob = cast(blob, POINTER(c_byte))
        credential.Persist = 2
        credential.UserName = "Spotify OAuth refresh token"
        if not self._advapi.CredWriteW(byref(credential), 0):
            raise CredentialStoreError("Windows no pudo guardar la autorización de Spotify.")

    def clear(self) -> None:
        if not self._advapi.CredDeleteW(self.target, 1, 0):
            error = windll.kernel32.GetLastError()
            if error != 1168:  # ERROR_NOT_FOUND
                raise CredentialStoreError("Windows no pudo eliminar la autorización de Spotify.")


class MemoryCredentialStore:
    """Implementación inyectable para pruebas; nunca escribe secretos en disco."""

    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str: return self.value
    def set(self, value: str) -> None: self.value = value
    def clear(self) -> None: self.value = ""
