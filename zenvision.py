import usb.core
import usb.util
import struct
import time

VENDOR_ID  = 0x0b05
PRODUCT_ID = 0x8835
CMD_EP     = 0x03

def open_device():
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
    if dev is None:
        raise RuntimeError("ZenVision panel not found")
    if dev.is_kernel_driver_active(0):
        dev.detach_kernel_driver(0)
    usb.util.claim_interface(dev, 0)   # no set_configuration() - already configured
    return dev

def send_cmd(dev, payload: bytes):
    buf = payload.ljust(512, b"\x00")
    dev.write(CMD_EP, buf)

def set_time(dev, dt=None, use_24h=True):
    dt = dt or time.localtime()
    payload = bytes([0x40, 0x09]) \
        + struct.pack("<H", dt.tm_year) \
        + bytes([dt.tm_mon, dt.tm_mday, dt.tm_hour, dt.tm_min, dt.tm_sec]) \
        + bytes([1 if use_24h else 0, 0x01])
    send_cmd(dev, payload)

set_time(open_device())