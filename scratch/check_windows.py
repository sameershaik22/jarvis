import ctypes
import os

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

def get_station_and_desktop():
    h_winsta = user32.GetProcessWindowStation()
    buf = ctypes.create_unicode_buffer(256)
    user32.GetUserObjectInformationW(h_winsta, 2, buf, 256, None) # 2 = UOI_NAME
    winsta_name = buf.value

    h_desk = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
    user32.GetUserObjectInformationW(h_desk, 2, buf, 256, None)
    desk_name = buf.value
    
    print(f"WindowStation: {winsta_name}, Desktop: {desk_name}")

if __name__ == "__main__":
    get_station_and_desktop()
