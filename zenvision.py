import usb.core
import usb.util
import struct
import time

VENDOR_ID  = 0x0b05
PRODUCT_ID = 0x8835

COMMAND_EP     = 0x03   # interrupt OUT, command channel
FRAMEBUFFER_EP = 0x07   # bulk OUT, framebuffer
RESPONSE_EP    = 0x82   # interrupt IN, response channel

# Open the panel (no kernel driver binds the vendor interface)
def open_device():
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
    if dev is None:
        raise RuntimeError("ZenVision panel not found")
    if dev.is_kernel_driver_active(0):
        dev.detach_kernel_driver(0)
    usb.util.claim_interface(dev, 0)
    return dev

# Send a command zero-padded to 512 bytes, read reply on EP 0x82 and return it
def send_cmd(dev, payload: bytes, timeout=3000):
    if len(payload) > 512:
        raise ValueError("Command payload exceeds 512 bytes")
    buf = payload.ljust(512, b"\x00")
    try:
        dev.write(COMMAND_EP, buf, timeout=timeout)
        return bytes(dev.read(RESPONSE_EP, 512, timeout=timeout))
    except usb.core.USBTimeoutError:
        return None

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

# 30 05 04 00 00 00 <x> - set battery icon
def set_battery(dev, battery: bool = True):
    x = 0x03 if battery else 0x01
    send_cmd(dev, bytes([0x30, 0x05, 0x04, 0x00, 0x00, x]))

# 35 01 <brightness> - set brightness level (raw bytes per level)
BRIGHTNESS = {1: 0x0f, 2: 0x4f, 3: 0xbc}
def set_brightness(dev, level: int = 2):
    assert level in BRIGHTNESS, "brightness must be 1-3"
    send_cmd(dev, bytes([0x35, 0x01, BRIGHTNESS[level]]))

# 32 02 <x> <x> - boot animation on/off
def set_boot_animation(dev, on: bool = True):
    x = 0x02 if on else 0x00
    send_cmd(dev, bytes([0x32, 0x02, x, x]))

# 40 09 <datetime> <format> <weekday> - set date and time (local time!)
def set_time(dev, dt=None, use_24h: bool = True):
    dt = dt or time.localtime()
    year_bytes = struct.pack("<H", dt.tm_year) # little-endian u16
    weekday = (dt.tm_wday + 1) % 7 # device: Sunday = 0, Python: Monday = 0
    send_cmd(dev, bytes([0x40, 0x09, *year_bytes, dt.tm_mon, dt.tm_mday, dt.tm_hour, dt.tm_min, dt.tm_sec, int(use_24h), weekday]))

# f1 03 <query> - content-engine state: '01' clock, '02' theme, '07' image
def get_engine_state(dev) -> str:
    return send_cmd(dev, bytes([0xf1, 0x03])).rstrip(b"\x00").decode("ascii")

# Full state-resync burst as MyASUS sends it, paced like the app
# (~265ms after time-set, ~1.5s before speed). Best-effort re-sync only:
# cannot revive a latched-off panel (see PROTOCOL.md CAUTION).
def resync(dev, speed: int = 3, theme: int = 4, brightness: int = 2, boot_animation: bool = True):
    set_battery(dev, on=True)
    time.sleep(0.05)
    send_cmd(dev, bytes([0x31, 0x02, 0x00, 0x04]))
    set_time(dev)
    time.sleep(0.3)
    set_boot_animation(dev, boot_animation)
    set_brightness(dev, brightness)
    time.sleep(1.5)
    set_speed(dev, speed)
    set_theme(dev, theme)

def power_off(dev):
    send_cmd(dev, bytes([0x30, 0x05, 0x04]))
    send_cmd(dev, bytes([0x31, 0x02, 0x00, 0x04]))

def power_on(dev):
    send_cmd(dev, bytes([0x30, 0x05, 0x04, 0x00, 0x00, 0x00, 0x03]))
    send_cmd(dev, bytes([0x30, 0x05, 0x02, 0x00, 0x04]))

# RECOVERY SEQUENCE
def recovery(dev):
    # power off
    send_cmd(dev, bytes([0x30, 0x05, 0x04]))
    send_cmd(dev, bytes([0x31, 0x02, 0x00, 0x04]))
    # power on
    send_cmd(dev, bytes([0x30, 0x05, 0x04, 0x00, 0x00, 0x00, 0x03])) #
    send_cmd(dev, bytes([0x31, 0x02, 0x00, 0x04]))
    send_cmd(dev, bytes([0x40, 0x09, 0xea, 0x07, 0x09, 0x0f, 0x14, 0x27, 0x00, 0x01, 0x02]))
    send_cmd(dev, bytes([0x32, 0x02, 0x02, 0x02]))
    send_cmd(dev, bytes([0x35, 0x01, 0x4f]))
    send_cmd(dev, bytes([0x33, 0x01, 0x02]))
    send_cmd(dev, bytes([0x30, 0x05, 0x02, 0x00, 0x04])) #

if __name__ == "__main__":
    dev = open_device()

    #send_cmd(dev, bytes([0x30, 0x05, 0x04, 0x00, 0x00, 0x00, 0x03]))
    #send_cmd(dev, bytes([0x31, 0x02, 0x02, 0x03])) #swipe
    #send_cmd(dev, bytes([0x31, 0x02, 0x00, 0x04])) #no swipe
    #set_clock(dev, 2)
    #set_time(dev)
    #set_speed(dev, 2)
    #set_theme(dev, 4)
    set_brightness(dev, 1)
    set_speed(dev, 1)
    power_off(dev)
    time.sleep(2)
    #recovery(dev)
    power_on(dev)