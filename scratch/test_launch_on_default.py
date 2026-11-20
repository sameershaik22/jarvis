import ctypes
import os
import time

user32 = ctypes.windll.user32

def test():
    # 1. Switch this thread to Default desktop
    h_default = user32.OpenDesktopW("Default", 0, False, 0x01FF)
    print("OpenDesktop handle:", h_default)
    if h_default:
        res = user32.SetThreadDesktop(h_default)
        print("SetThreadDesktop result:", res)
    
    # 2. Check windows on Default desktop now!
    def cb(hwnd, extra):
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if title:
            print("Visible window on Default:", title[:60])
        return True
    
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    print("Enumerating windows on Default desktop:")
    user32.EnumWindows(CB(cb), 0)

if __name__ == "__main__":
    test()

