"""Windows Explorer file drops for a Tk window."""
import ctypes
import queue
import sys
from ctypes import wintypes


def enable_file_drop(root, on_drop):
    if sys.platform != "win32":
        return
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    pointer = ctypes.c_ssize_t
    procedure = ctypes.WINFUNCTYPE(pointer, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, pointer]
    user32.SetWindowLongPtrW.restype = pointer
    user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.CallWindowProcW.restype = pointer
    shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
    shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
    shell32.DragQueryFileW.restype = wintypes.UINT
    shell32.DragFinish.argtypes = [wintypes.HANDLE]
    root.update_idletasks()
    hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
    pending = queue.SimpleQueue()
    active = True

    def deliver():
        if not active:
            return
        try:
            while not pending.empty():
                on_drop(pending.get_nowait())
        finally:
            if active:
                root._file_drop_timer = root.after(100, deliver)

    @procedure
    def receive(window, message, wparam, lparam):
        if message == 0x0233:  # WM_DROPFILES
            paths = []
            try:
                count = shell32.DragQueryFileW(wparam, 0xFFFFFFFF, None, 0)
                for index in range(count):
                    length = shell32.DragQueryFileW(wparam, index, None, 0)
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    shell32.DragQueryFileW(wparam, index, buffer, length + 1)
                    paths.append(buffer.value)
            finally:
                shell32.DragFinish(wparam)
            # Windows calls this during native message dispatch. Defer every
            # Tk operation to Tk's own event loop to avoid reentrant callbacks.
            pending.put(paths)
            return 0
        return user32.CallWindowProcW(previous, window, message, wparam, lparam)

    previous = user32.SetWindowLongPtrW(hwnd, -4, ctypes.cast(receive, ctypes.c_void_p).value)
    if not previous:
        raise ctypes.WinError(ctypes.get_last_error())
    root._file_drop_callback = receive
    shell32.DragAcceptFiles(hwnd, True)
    root._file_drop_timer = root.after(100, deliver)

    def detach(event):
        nonlocal active
        if event.widget is root:
            active = False
            root.after_cancel(root._file_drop_timer)
            shell32.DragAcceptFiles(hwnd, False)
            user32.SetWindowLongPtrW(hwnd, -4, previous)

    root.bind("<Destroy>", detach, add="+")
