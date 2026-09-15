import usb.core
import usb.util
import struct
import time

VENDOR_ID  = 0x0b05
PRODUCT_ID = 0x8835
CMD_EP     = 0x03   # interrupt OUT, command channel
IMG_EP     = 0x07   # bulk OUT, framebuffer

# Device Setup
def open_device():
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
    if dev is None:
        raise RuntimeError("(0b05:8835) ZenVision panel not found")
    if dev.is_kernel_driver_active(0):
        dev.detach_kernel_driver(0)
    usb.util.claim_interface(dev, 0) # no set_configuration() - already configured
    return dev

# Send command zero-padded to 512 bytes
def send_cmd(dev, payload: bytes):
    buf = payload.ljust(512, b"\x00")
    dev.write(CMD_EP, buf)

# 33 01 <speed> - set animation speed
def set_speed(dev, speed: int):
    assert speed in range(1, 4), "speed must be 1-3"
    send_cmd(dev, bytes([0x33, 0x01, speed]))

# 30 05 02 00 <theme> - set built-in theme
def set_theme(dev, theme: int):
    assert theme in range(1, 5), "theme must be 1-4"
    send_cmd(dev, bytes([0x30, 0x05, 0x02, 0x00, theme]))

# 30 05 01 <clock> - set clock display layout
def set_clock(dev, clock: int):
    assert clock in range(1, 3), "clock must be 1-2"
    send_cmd(dev, bytes([0x30, 0x05, 0x01, clock]))

# 30 05 04 00 00 <flag> - set show battery on clock display
def set_show_battery(dev, show_battery: bool = True):
    flag = 0x03 if show_battery else 0x01
    send_cmd(dev, bytes([0x30, 0x05, 0x04, 0x00, 0x00, flag]))

# 40 09 <datetime> <format> 01 — set date and time
def set_time(dev, dt=None, use_24h: bool = True):
    dt = dt or time.localtime()
    year_bytes = struct.pack("<H", dt.tm_year) # convert year to little-endian 2-byte representation
    send_cmd(dev, bytes([0x40, 0x09, *year_bytes, dt.tm_mon, dt.tm_mday, dt.tm_hour, dt.tm_min, dt.tm_sec, int(use_24h), 0x01]))

if __name__ == "__main__":
    dev = open_device()

    set_time(dev)