# ASUS ZenVision (UX5401ZAS) — USB Protocol Notes

Device: `0b05:8835` (Nuvoton M480, "M480 BULK"), Interface 0 (vendor-specific, class 0xFF).

Reverse-engineered from `record9.pcapng`, a 108-frame Wireshark/USBPcap
capture where every command burst was tagged at capture time with the exact
action taken in the ASUS app (MyASUS / Armoury Crate).

## Endpoints

| Endpoint | Direction | Type | Role |
|---|---|---|---|
| `0x03` | OUT | Interrupt, 512B | **Command channel** — every command below |
| `0x07` | OUT | Bulk | Pixel/framebuffer data (256×64, 4-bit grayscale) — not present in this capture, format not re-verified here |
| `0x82` | IN | Interrupt | Telemetry/status. One observed 4-byte reply (`40 9a 10 00`) doesn't decode as a valid timestamp either byte order — unidentified |

All commands below are host→device, padded to 512 bytes; only the leading
bytes carry meaning. Nothing meaningful comes back on EP3 in response.

## Command reference

### `33 01 <speed>` — Set animation/effect speed
```
33 01 01   speed 1
33 01 02   speed 2
33 01 03   speed 3
```
Confirmed across built-in themes, both clock modes, and text templates — the
same speed command is reused for whatever content is currently active.

### `30 05 02 00 <idx>` — Select built-in ASUS theme
```
30 05 02 00 01   Theme 1
30 05 02 00 02   Theme 2
30 05 02 00 03   Theme 3
30 05 02 00 04   Theme 4
```
Sent immediately after the matching `33 01 <speed>`.

### `30 05 01 <mode>` — Select clock layout mode
```
30 05 01 01   Time mode 1
30 05 01 02   Time mode 2
```
Followed by a `33 01 <speed>` and a `40 09 ...` time-set command.

### `30 05 04 00 00 <flags>` — Clock display options
```
30 05 04 00 00 03   battery status ON   (0b011)
30 05 04 00 00 01   battery status OFF  (0b001)
```
Bitmask: bit0 constant/always set in every sample (purpose unconfirmed), bit1
= show battery percentage. Only one flag was exercised, so other bits are
unverified. Switching 24h↔12h format does **not** touch this byte.

### `40 09 <date/time>` — Set RTC / wall-clock time
```
byte 0     0x40                     opcode
byte 1     0x09                     constant sub-type marker
byte 2-3   year, little-endian u16  e.g. 2026 → ea 07
byte 4     month (1-12, binary)
byte 5     day (1-31, binary)
byte 6     hour (0-23, binary — always stored as 24h internally)
byte 7     minute (0-59, binary)
byte 8     second (0-59, binary)
byte 9     display-format flag: 1 = show as 24h, 0 = show as 12h
byte 10    constant 0x01 in every sample here — meaning unresolved
rest       zero-padded to 512 bytes
```
All fields are **local wall-clock time**, not UTC, not epoch. The 12h/24h
toggle only changes byte 9 — the stored hour value itself is always 24h
binary, confirmed by comparing the "12hr" and "24hr" test cases side by side.

### `31 02 <a> <b>` — Select content-engine mode
```
31 02 00 04   image-backed content (custom images, personal labels — anything
              rendered client-side and pushed as a bitmap)
31 02 02 03   procedurally-rendered content (Time mode 2; also re-entered when
              a Text Template's filter is switched back to "none")
```
Sent before the corresponding `30 06 05 ...` apply command. Only two
combinations were observed — value space beyond these two is unknown.

### `30 06 05 00 00 00 <val>` — Apply/commit content
```
30 06 05 00 00 00 02   after any image-backed content (SAMPLE_IMAGE,
                        SAMPLE_IMAGE2, all 6 Personal Labels) — constant,
                        verified byte-for-byte identical across every filter
                        tested (hatch door / circuit / scout / geomagnetic
                        sandstorm) — see note below
30 06 05 00 00 00 03   Text Template, filter "news ticker"
30 06 05 00 00 00 01   Text Template, filter "none"
```
**Filters on image content are not set by any command-channel packet.** Every
byte of this 512-byte command was diffed across all five image/filter
combinations captured and is identical in every case, and no other packet
appears between content-select and apply for those actions. Given the panel
is a pushed framebuffer (not a DRM display), the filter must be baked into
the bitmap client-side before the bulk upload. Text Templates are the
exception — there the byte genuinely changes with the chosen filter, meaning
that's a real device-side effect applied to procedurally-rendered text, not
to images.

## Observed sequences per action

| App action | Command sequence |
|---|---|
| Pick Theme N, speed S | `33 01 <S>` → `30 05 02 00 <N>` |
| Time Mode 1, format F, battery B, speed S | `30 05 04 00 00 <flags(B)>` → `33 01 <S>` → `30 05 01 01` → `40 09 ...<time>...<F-flag>...` |
| Time Mode 2, speed S | `31 02 02 03` → `30 05 01 02` → `40 09 ...` |
| Apply custom/sample image or personal label | `31 02 00 04` → `30 06 05 00 00 00 02` → (framebuffer on EP `0x07`) |
| Apply Text Template, filter F | `31 02 00 04` or `31 02 02 03` (re-entry) → `30 06 05 00 00 00 <filterID>` → `33 01 <S>` |

## Sending commands — worked examples

The device enumerates as a plain vendor-class interface, so no kernel driver
binds it; `pyusb` (via libusb) is the simplest way to talk to it, matching
how `zenvision-linux` approaches the panel.

```python
import usb.core
import usb.util
import struct
import time

VENDOR_ID  = 0x0b05
PRODUCT_ID = 0x8835
CMD_EP     = 0x03   # interrupt OUT, command channel
IMG_EP     = 0x07   # bulk OUT, framebuffer

def open_device():
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
    if dev is None:
        raise RuntimeError("ZenVision panel not found")
    if dev.is_kernel_driver_active(0):
        dev.detach_kernel_driver(0)
    dev.set_configuration()
    usb.util.claim_interface(dev, 0)
    return dev

def send_cmd(dev, payload: bytes):
    """Pad to 512 bytes and write on the interrupt command channel."""
    buf = payload.ljust(512, b"\x00")
    dev.write(CMD_EP, buf)

def send_image(dev, framebuffer: bytes):
    """framebuffer: pre-rendered 256x64, 4-bit grayscale, already
    filtered/effected client-side if you want a visual filter applied."""
    send_cmd(dev, bytes([0x31, 0x02, 0x00, 0x04]))
    send_cmd(dev, bytes([0x30, 0x06, 0x05, 0x00, 0x00, 0x00, 0x02]))
    dev.write(IMG_EP, framebuffer)
```

### Set the time (and 12h/24h format)

```python
def set_time(dev, dt=None, use_24h=True):
    dt = dt or time.localtime()  # MUST be local time, not UTC
    payload = bytes([0x40, 0x09]) \
        + struct.pack("<H", dt.tm_year) \
        + bytes([dt.tm_mon, dt.tm_mday, dt.tm_hour, dt.tm_min, dt.tm_sec]) \
        + bytes([1 if use_24h else 0, 0x01])  # last byte: unresolved, mirror observed constant
    send_cmd(dev, payload)

set_time(open_device())  # sends current local time, 24h display
```

### Set battery-status visibility (clock mode 1 only)

```python
def set_clock_options(dev, show_battery: bool):
    flags = 0x03 if show_battery else 0x01
    send_cmd(dev, bytes([0x30, 0x05, 0x04, 0x00, 0x00, flags]))

def enable_time_mode_1(dev, speed=2, show_battery=True, use_24h=True):
    set_clock_options(dev, show_battery)
    send_cmd(dev, bytes([0x33, 0x01, speed]))
    send_cmd(dev, bytes([0x30, 0x05, 0x01, 0x01]))
    set_time(dev, use_24h=use_24h)
```

### Select a built-in animated theme

```python
def select_theme(dev, theme_idx: int, speed: int = 2):
    assert 1 <= theme_idx <= 4
    assert 1 <= speed <= 3
    send_cmd(dev, bytes([0x33, 0x01, speed]))
    send_cmd(dev, bytes([0x30, 0x05, 0x02, 0x00, theme_idx]))

select_theme(open_device(), theme_idx=3, speed=1)
```

### Push a static image

```python
from PIL import Image

def load_framebuffer(path: str) -> bytes:
    img = Image.open(path).convert("L").resize((256, 64))
    px = list(img.getdata())
    # pack two 4-bit grayscale pixels per byte (format per zenvision-linux README;
    # re-verify against a captured EP 0x07 payload before relying on this)
    out = bytearray()
    for i in range(0, len(px), 2):
        hi = px[i] >> 4
        lo = (px[i + 1] >> 4) if i + 1 < len(px) else 0
        out.append((hi << 4) | lo)
    return bytes(out)

dev = open_device()
send_image(dev, load_framebuffer("logo.png"))
```

The pixel-packing in `load_framebuffer` follows the framebuffer format stated
in the `zenvision-linux` README (256×64, 4-bit grayscale) but wasn't
independently confirmed against a bulk-endpoint capture in this pass — worth
double-checking with your own EP `0x07` capture before shipping it.

## Open questions

- **Byte 10 of the `40 09` time-set command.** Constant `0x01` in every
  record9 sample. In an earlier, less-controlled two-sample capture on a
  different day, this same byte was seen as `0x00` once — but nothing in
  that earlier capture was logged well enough to say what differed between
  the two sessions. Needs a dedicated test that isolates just this byte.
- **`30 05 04 00 00 <flags>` bit 0.** Always `1`; never toggled off in
  testing. Unknown whether it's a live flag or a fixed header bit.
- **Full filter-ID space for Text Templates.** Only `01` (none) and `03`
  (news ticker) observed.
- **`31 02 <a> <b>` value space.** Only `00 04` and `02 03` observed.
- **EP `0x82` IN status word** (`40 9a 10 00`) — doesn't decode as a
  timestamp either byte order; unidentified.
- **Bulk framebuffer format on EP `0x07`** — out of scope for this capture
  (command-channel only); the packing above is taken from the
  `zenvision-linux` README, not independently re-verified here.
- **Brightness** — no command found, and no corresponding control exists in
  the ASUS app UI. Treat as unconfirmed/likely nonexistent.

## Comparison to the original `zenvision-linux` protocol docs

What this pass confirms was **right**:
- Device identity (`0b05:8835`), interface 0 as vendor-specific/class 0xFF.
- Endpoint roles: `0x03` interrupt-OUT as the command channel, `0x07` bulk-OUT
  for framebuffer data, `0x82` interrupt-IN returning non-actionable status.
- The general shape of commands: short meaningful prefix, zero-padded to a
  512-byte buffer, `0x30`-family opcodes for apply/configure actions,
  `0x31`-family for content-mode selection.
- The autonomous/built-in-theme behavior description (MCU free-runs its own
  themes, including the clock, when nothing is actively driving the panel).

What this pass found **wrong or incomplete**:
- **Theme selection was misattributed.** The original docs' guess of
  `33 01 IDX` as theme-select is actually the **speed** command; the real
  theme-select is `30 05 02 00 IDX`.
- **No time-set command was documented at all.** `40 09 ...` (the RTC/clock
  command that drives the lid-close clock animation) doesn't appear in the
  original protocol notes.
- **No clock-mode, battery-status, or text-template/personal-label commands
  were documented** — this pass adds `30 05 01`, `30 05 04`, `31 02`, and the
  `30 06 05` apply variants.
- **Brightness was assumed to exist** with no supporting evidence found here
  or in the ASUS app's own UI.