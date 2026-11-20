import ctypes
import os
import subprocess

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

def test_open_desktop():
    h_default = user32.OpenDesktopW("Default", 0, False, 0x01FF) # MAXIMUM_ALLOWED or GENERIC_ALL
    print("OpenDesktop('Default') handle:", h_default)
    if h_default:
        res = user32.SetThreadDesktop(h_default)
        print("SetThreadDesktop('Default') result:", res)
        
        # Check current desktop name now
        buf = ctypes.create_unicode_buffer(256)
        user32.GetUserObjectInformationW(h_default, 2, buf, 256, None)
        print("New thread desktop:", buf.value)

if __name__ == "__main__":
    test_open_desktop()

