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

# 30 05 01 <clock> set clock display layout
def set_clock(dev, clock: int):
    assert clock in range(1, 3), "clock must be 1-2"
    send_cmd(dev, bytes([0x30, 0x05, 0x01, clock]))

# 30 05 02 00 <theme> set built-in theme
def set_theme(dev, theme: int):
    assert theme in range(1, 5), "theme must be 1-4"
    send_cmd(dev, bytes([0x30, 0x05, 0x02, 0x00, theme]))

# 30 05 04 00 00 00 <val> set battery icon
def set_battery(dev, battery: bool = True):
    x = 0x03 if battery else 0x01
    send_cmd(dev, bytes([0x30, 0x05, 0x04, 0x00, 0x00, x]))

# 30 06 05 00 00 00 00 <mode> set content mode
def set_content_mode(dev, mode: int):
    assert mode in range(1, 4), "mode must be 1-3"
    send_cmd(dev, bytes([0x30, 0x06, 0x05, 0x00, 0x00, 0x00, 0x00, mode]))

# 31 02 <a> <b> set screen sweep
def set_screen_sweep(dev, sweep: bool = False):
    x = 0x02 if sweep else 0x00
    y = 0x03 if sweep else 0x04
    send_cmd(dev, bytes([0x31, 0x02, x, y]))

# 32 02 <a> <b> boot animation on/off
def set_boot_animation(dev, on: bool = True):
    x = 0x02 if on else 0x00
    send_cmd(dev, bytes([0x32, 0x02, x, x]))

# 33 01 <speed> set animation speed
def set_speed(dev, speed: int):
    assert speed in range(1, 4), "speed must be 1-3"
    send_cmd(dev, bytes([0x33, 0x01, speed]))

# 35 01 <brightness> set brightness level (1-3) or value (0-255)
BRIGHTNESS = {1: 0x0f, 2: 0x4f, 3: 0xbc}
def set_brightness(dev, value: int):
    assert 0 <= value <= 0xff, "brightness value must be 0-255"
    send_cmd(dev, bytes([0x35, 0x01, value]))

# 40 09 <datetime> <format> <weekday> set date and time
def set_time(dev, dt=None, use_24h: bool = True):
    dt = dt or time.localtime()
    year_bytes = struct.pack("<H", dt.tm_year) # little-endian u16
    weekday = (dt.tm_wday + 1) % 7 # device: Sunday = 0, Python: Monday = 0
    send_cmd(dev, bytes([0x40, 0x09, *year_bytes, dt.tm_mon, dt.tm_mday, dt.tm_hour, dt.tm_min, dt.tm_sec, int(use_24h), weekday]))

# f1 03 query content state
def get_engine_state(dev) -> str:
    # response: '01' clock, '02' theme, '07' image
    return send_cmd(dev, bytes([0xf1, 0x03])).rstrip(b"\x00").decode("ascii")

# power off
def power_off(dev):
    send_cmd(dev, bytes([0x30, 0x05, 0x04, 0x00, 0x00, 0x00, 0x00])) # power off
    send_cmd(dev, bytes([0x31, 0x02, 0x00, 0x04])) # screen sweep off

# power on
def power_on(dev):
    send_cmd(dev, bytes([0x30, 0x05, 0x04, 0x00, 0x00, 0x00, 0x03])) # battery on/off (on)
    send_cmd(dev, bytes([0x30, 0x05, 0x02, 0x00, 0x04])) # any theme (theme 4)

if __name__ == "__main__":
    dev = open_device()

### Example usage:

    # set_speed(dev, 2)                  # choose 1-3
    # set_theme(dev, 4)                  # choose 1-4
    # set_brightness(dev, BRIGHTNESS[1]) # choose 1-3
    # set_time(dev)

### Commands Sequences from MyASUS app

### Select theme

    # set_speed(dev, 2)                  # choose 1-3
    # set_theme(dev, 4)                  # choose 1-4

### Select clock layout

    ## clock 1

    # set_battery(dev, True)             # choose True/False
    # set_clock(dev, 1)
    # set_speed(dev, 2)                  # choose 1-3
    # set_time(dev, use_24h=True)        # choose True/False

    ## clock 2

    # set_screen_sweep(dev, True)
    # set_clock(dev, 2)
    # set_speed(dev, 2)                  # choose 1-3
    # set_time(dev, use_24h=True)        # choose True/False

### Other 

    # set_boot_animation(dev, True)      # choose True/False
    # set_brightness(dev, BRIGHTNESS[1]) # choose 1-3

## Power

    # power_off(dev)
    # power_on(dev)