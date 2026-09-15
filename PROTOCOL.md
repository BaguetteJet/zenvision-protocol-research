# ASUS ZenVision (UX5401ZAS) — USB Protocol Notes

Device: `0b05:8835` (Nuvoton M480, "M480 BULK"), Interface 0 (vendor-specific, class 0xFF).

Reverse-engineered from USBPcap/Wireshark captures, where every command
burst was tagged at capture time with the exact action taken in the ASUS app
(MyASUS / Armoury Crate):

| Capture | What it covers |
|---|---|
| `record9` | Themes, clock modes, time-set, content apply (command channel only) |
| `record10` | Lid close behavior, brightness, continuous image streaming (EP `0x07`) |
| `record11` | Brightness levels, boot-animation toggle, display off/on |
| `record12` | Brightness level 2, full state-resync burst |
| `record13` | Display off/on with the full state-resync burst |
| `record14` | Clock modes (`f1 03` + EP `0x82` reply), Text Template filters (None / New ticker), bulk-frame framing |

## Endpoints

| Endpoint | Direction | Type | Role |
|---|---|---|---|
| `0x03` | OUT | Interrupt, 512B | **Command channel** — every command below |
| `0x07` | OUT | Bulk | Pixel/framebuffer data (256×64, 4-bit grayscale) — 8704-byte chunks, see framing below |
| `0x82` | IN | Interrupt | Telemetry/status. Replies to queries with short status words: `30 31` after the `f1 03` command (record14). One earlier 4-byte reply (`40 9a 10 00`, record9) doesn't decode as a timestamp — unidentified |

All commands below are host→device, padded to 512 bytes; only the leading
bytes carry meaning. Nothing meaningful comes back on EP3 in response.

## Command reference

Every command is a fixed **512-byte** interrupt-OUT transfer on EP `0x03`.
Only the leading bytes shown per command carry meaning — everything after
them is `0x00` padding out to the full 512 bytes. This applies to every
command below, including the full-frame examples.

### `33 01 <speed>` — Set animation/effect speed
```
33 01 01   speed 1
33 01 02   speed 2
33 01 03   speed 3
```
Confirmed across built-in themes, both clock modes, and text templates — the
same speed command is reused for whatever content is currently active.

**Full frame example (speed 2):**
```
33 01 02 00 00 00 00 00 00 00 00 00 00 00 00 00 ... (zero-padded to 512 bytes)
```
Only the first 3 bytes carry meaning; bytes 3–511 are `0x00`.

### `35 01 <val>` — Set brightness

Raw byte value, not an index. Observed levels:

```
35 01 0F   brightness level 1
35 01 4F   brightness level 2
35 01 BC   brightness level 3
```

Levels 1 and 3 were tagged in record11 ("Set brightness 1" / "Set
brightness 3"); level 2 (`4f`) was tagged "Brightness 2" in record12 and is
also the value used in record10's lid-close burst. The three values are not
linear (0x0f / 0x4f / 0xbc) — these are the exact raw bytes MyASUS sends.
Intermediate levels were not exercised.

**Full frame example (brightness level 2):**
```
35 01 4F 00 00 00 00 00 00 00 00 00 00 00 00 00 ... (zero-padded to 512 bytes)
```
Only the first 3 bytes carry meaning; the rest of the 512-byte buffer is `0x00`.

### `32 02 <a> <b>` — Boot-animation toggle

```
32 02 02 02   boot animation ON
32 02 00 00   boot animation OFF
```

Cleanly binary — confirmed across two toggles in record11 ("Boot Animation
On" / "Boot Animation Off") and present in record12/13's resync bursts.

**Full frame example (boot animation ON):**
```
32 02 02 02 00 00 00 00 00 00 00 00 00 00 00 00 ... (zero-padded to 512 bytes)
```
Only the first 4 bytes carry meaning; the rest of the 512-byte buffer is `0x00`.

### `30 05 02 00 <idx>` — Select built-in ASUS theme
```
30 05 02 00 01   Theme 1
30 05 02 00 02   Theme 2
30 05 02 00 03   Theme 3
30 05 02 00 04   Theme 4
```
Sent immediately after the matching `33 01 <speed>`.

**Full frame example (Theme 3):**
```
30 05 02 00 03 00 00 00 00 00 00 00 00 00 00 00 ... (zero-padded to 512 bytes)
```
Only the first 5 bytes carry meaning; the rest of the 512-byte buffer is `0x00`.

### `30 05 01 <mode>` — Select clock layout mode
```
30 05 01 01   Time mode 1
30 05 01 02   Time mode 2
```
Followed by a `33 01 <speed>` and a `40 09 ...` time-set command.

**Full frame example (Time mode 2):**
```
30 05 01 02 00 00 00 00 00 00 00 00 00 00 00 00 ... (zero-padded to 512 bytes)
```
Only the first 4 bytes carry meaning; the rest of the 512-byte buffer is `0x00`.

### `30 05 04 00 00 <flags>` — Panel flags (display power + battery)

A general panel-enable bitmask — the same command carries different flags in
different contexts:

| Flags | record9 (clock mode 1) | record11/12/13 |
|---|---|---|
| `00` | — | **display OFF** |
| `01` | battery percentage **hidden** | — |
| `03` | battery percentage **shown** | **display ON** |

Interpretation: bit0 = display/panel enabled, bit1 = show battery percentage
on the clock display. In record9 every sample was `01` or `03` because the
display was on throughout that session; in record11/12/13 the display off/on
toggles moved the same byte between `00` and `03`. Only these two bits were
observed — other bits are unverified. Switching 24h↔12h format does **not**
touch this byte.

#### ⚠️ Display off is sticky — do not send flags-only off

A Linux-driver test (flags-only off, `30 05 04 00 00 00`, no follow-up
burst) left the panel **permanently black**: screen off, no lid-close clock
animation, and it could **not** be revived by any of

- flags-only on: `30 05 04 00 00 03` or `30 05 04 00 00 01`
- theme commands (`33 01` + `30 05 02 00 <idx>`)
- a full Windows reboot

Only the ASUS app's Display Off → Display On cycle brought it back. The app
**never** sends the flags byte alone — off is `30 05 04 00 00 00` followed
by `31 02 00 04`, and on is `30 05 04 00 00 03` followed by the **full
state-resync burst** (record13):

```
30 05 04 00 00 03   display on
31 02 00 04          content-engine select
40 09 <time>         time-set
32 02 02 02          boot animation on
35 01 <brightness>   brightness
33 01 <speed>        speed
30 05 02 00 <theme>  theme
```

Probable cause: the off command powers down the panel controller into a
low-power state; re-initializing it requires the complete content/state
push, not just a register bit. **Recommendation: treat `30 05 04 00 00 00`
as a last resort, and wake the panel with the full burst above (`resync()`
in `zenvision.py`), never with the flags byte alone.**

**Full frame example (display ON):**
```
30 05 04 00 00 03 00 00 00 00 00 00 00 00 00 00 ... (zero-padded to 512 bytes)
```
Only the first 6 bytes carry meaning; the rest of the 512-byte buffer is `0x00`.

### `40 09 <date/time>` — Set RTC / wall-clock time

| Byte(s) | Field | Encoding |
|---|---|---|
| 0 | opcode | `0x40` |
| 1 | sub-type marker | constant `0x09` |
| 2–3 | year | little-endian u16 (e.g. 2026 → `ea 07`) |
| 4 | month | binary, 1–12 |
| 5 | day | binary, 1–31 |
| 6 | hour | binary, 0–23 — always stored as 24h internally |
| 7 | minute | binary, 0–59 |
| 8 | second | binary, 0–59 |
| 9 | display-format flag | `1` = show as 24h, `0` = show as 12h |
| 10 | day of week | `0` = Sunday … `6` = Saturday. Observed: Sun `00`, Mon `01`, Tue `02` |
| 11–511 | padding | zero-filled to 512 bytes total |

All fields are **local wall-clock time**, not UTC, not epoch. The 12h/24h
toggle only changes byte 9 — the stored hour value itself is always 24h
binary, confirmed by comparing the "12hr" and "24hr" test cases side by side.
Byte 10 is the day of the week, Sunday = 0: across sessions on three real
dates — Sep 13 (Sun) → `00`, Sep 14 (Mon) → `01`, Sep 15 (Tue) → `02`.

**Worked byte examples:**

*Sep 15, 2026 (Tue), 14:30:00, 24h display:*
```
40 09 EA 07 09 0F 0E 1E 00 01 02 00 00 00 00 00 ... (zero-padded to 512 bytes)
```
| `40` | `09` | `EA 07` | `09` | `0F` | `0E` | `1E` | `00` | `01` | `02` |
|---|---|---|---|---|---|---|---|---|---|
| opcode | marker | year 2026 | month 9 | day 15 | hour 14 | min 30 | sec 0 | 24h | Tue |

*Dec 25, 2026 (Fri), 08:05:30, 12h display:*
```
40 09 EA 07 0C 19 08 05 1E 00 01 05 00 00 00 00 ... (zero-padded to 512 bytes)
```
| `40` | `09` | `EA 07` | `0C` | `19` | `08` | `05` | `1E` | `00` | `05` |
|---|---|---|---|---|---|---|---|---|---|
| opcode | marker | year 2026 | month 12 | day 25 | hour 8 | min 5 | sec 30 | 12h | Fri |

Note the hour is `08` (24h binary) in both examples' internal representation
even though the second example displays in 12h mode — only byte 9 changes how
it's rendered on the panel, never the stored hour value itself.

### `f1 03` — Clock commit / status query (unidentified)

```
f1 03 00 00 ...
```

Sent ~1.5 s **after** the `40 09` time-set whenever a clock mode is
(re)configured in the app (record14, both Time mode 1 and Time mode 2). It
elicits a 512-byte interrupt-IN reply on EP `0x82`:

```
30 31 00 00 00 ... (zero-padded to 512 bytes)
```

The reply's leading bytes `30 31` are ASCII `"01"` — plausibly a status/ack
code, but its meaning is unconfirmed. Notably, `f1 03` is **not** sent in
the automatic display-on resync burst (record13) or the lid-close burst
(record10), which both contain a `40 09` time-set without it — so it seems
to be part of explicit clock-setting, not the generic state push.

### `31 02 <a> <b>` — Select content-engine mode
```
31 02 00 04   image-backed content (custom images, personal labels — anything
              rendered client-side and pushed as a bitmap)
31 02 02 03   procedurally-rendered content (Time mode 2; also re-entered when
              a Text Template's filter is switched back to "none")
```
Sent before the corresponding `30 06 05 ...` apply command. Only two
combinations were observed — value space beyond these two is unknown. In
record10's lid-close burst `31 02 00 04` is sent as a generic resync prelude
before re-selecting a built-in theme.

**Full frame example (image-backed content):**
```
31 02 00 04 00 00 00 00 00 00 00 00 00 00 00 00 ... (zero-padded to 512 bytes)
```
Only the first 4 bytes carry meaning; the rest of the 512-byte buffer is `0x00`.

### `30 06 05 00 00 00 <val>` — Apply/commit content
```
30 06 05 00 00 00 02   image-backed content (SAMPLE_IMAGE, SAMPLE_IMAGE2,
                        all 6 Personal Labels) — constant, verified
                        byte-for-byte identical across every filter tested
                        (hatch door / circuit / scout / geomagnetic
                        sandstorm). The filter's animation lives entirely in
                        the streamed pixel data, not in this byte.
30 06 05 00 00 00 03   Text Template, filter "news ticker"
30 06 05 00 00 00 01   Text Template, filter "none"
```
Filter IDs for Text Templates are now confirmed across two sessions
(record9 + record14): `01` = none, `03` = news ticker. Both push a **single**
8704-byte framed frame (see framing below) whose text bitmap is identical —
the filter byte is the only difference, so the animation is device-side:
- filter **none** → the device plays a horizontal-line wipe that "cleans"
  the screen before showing the text. (Quirk observed in the app: setting
  Time mode 2 makes the app push a none-filtered text frame first, so the
  wipe animation plays even though "none" isn't an option for the clock.)
- filter **news ticker** → the device scrolls the text.

**Full frame example (apply image content):**
```
30 06 05 00 00 00 02 00 00 00 00 00 00 00 00 00 ... (zero-padded to 512 bytes)
```
Only the first 7 bytes carry meaning; the rest of the 512-byte buffer is `0x00`.

## Observed sequences per action

| App action | Command sequence |
|---|---|
| Pick Theme N, speed S | `33 01 <S>` → `30 05 02 00 <N>` |
| Set brightness level B | `35 01 <raw(B)>` |
| Toggle boot animation | `32 02 02 02` (on) / `32 02 00 00` (off) |
| Display off | `30 05 04 00 00 00` → `31 02 00 04` — **sticky, see warning above** |
| Display on (recovery) | `30 05 04 00 00 03` → `31 02 00 04` → `40 09 ...` → `32 02 02 02` → `35 01 ...` → `33 01 ...` → `30 05 02 00 ...` |
| Time Mode 1, format F, battery B, speed S | `30 05 04 00 00 <flags(B)>` → `33 01 <S>` → `30 05 01 01` → `40 09 ...` → `f1 03` |
| Time Mode 2, speed S | `31 02 02 03` → `30 05 01 02` → `40 09 ...` → `f1 03` |
| Apply custom/sample image or personal label | `31 02 00 04` → `30 06 05 00 00 00 02` → (continuous pixel stream on EP `0x07`) |
| Apply Text Template, filter F | `31 02 00 04` (or `31 02 02 03` re-entry) → `30 06 05 00 00 00 <filterID>` → single 8704-byte frame → `33 01 <S>` |
| **Lid close** (full state resync) | `40 09 ...` → `35 01 ...` → `31 02 00 04` → `33 01 ...` → `30 05 02 00 ...` |

## Lid-close behavior (record10)

At the moment the lid closes, nothing happens immediately. The resync burst
fires **9.2 seconds later** (pcapng timestamps: CLOSE LID marker at t=0,
`40 09` at t≈9.2 s), then nothing at reopen — no second time-set, and no
command traffic at all between the resync and the next user action. Exact
burst from record10 (Sep 15, 2026, 18:01:19, brightness 2, speed 3, theme 4):

```
40 09 EA 07 09 0F 12 01 13 01 02   time-set (current local time + weekday)
35 01 4F                           brightness
31 02 00 04                        generic resync prelude
33 01 03                           speed
30 05 02 00 04                     theme
```

So the lid clock is driven by a single one-shot resync at lid-close, not by
continuous time updates and not at wake. A Linux driver should hook the
lid-close event and push this same burst — current local time included —
right before the display goes to sleep. (record11/12/13 show the same burst
with the display-flags and boot-animation commands prepended:

```
30 05 04 00 00 03 → 31 02 00 04 → 40 09 ... → 32 02 ... → 35 01 ... → 33 01 ... → 30 05 02 00 ...
```

)

## Bulk endpoint `0x07` — framing and streaming

Every bulk chunk is an **8704-byte** frame consisting of **17 × 512-byte
packets** (verified against full pcapng payloads from records 10 and 14):

| Packet byte(s) | Meaning |
|---|---|
| byte 0 | packet index `0x00`–`0x10` |
| byte 1 | `0x00`, except packet 16 which carries `0x01` as an end marker |
| bytes 2–3 | reserved, `0x00` |
| bytes 4–511 | payload (508 bytes per packet) |

Concatenating the payload of packets 0–15 (16 × 508 = 8128 bytes) plus the
first 64 payload bytes of packet 16 yields the **8192-byte 4bpp framebuffer**
(256×64, row-major, two 4-bit pixels per byte). This confirms the framing
described in the original `zenvision-linux` docs; the 4-bit pixel packing
itself (including the old docs' per-4-pixel pair swap) has still not been
independently re-verified against a rendered capture.

How frames are sent depends on content type:

- **Image-backed content** (sample images, personal labels, image filters):
  a **continuous stream** of frames — record10 shows 538 chunks ~60–70 ms
  apart, changing frame-to-frame for as long as the content stays active.
  "Filters" like hatch door / circuit are live animations pushed as a
  video-like stream, which is why the apply command's byte never changes:
  the filter lives in the pixels, not in the command.
- **Text Templates**: a **single** frame per apply (record14). The text
  bitmap is identical across filters — the chosen filter (`01` none / `03`
  news ticker) is applied device-side as an animation.

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
```

### Set the time (and 12h/24h format)

```python
def set_time(dev, dt=None, use_24h=True):
    dt = dt or time.localtime()  # MUST be local time, not UTC
    payload = bytes([0x40, 0x09]) \
        + struct.pack("<H", dt.tm_year) \
        + bytes([dt.tm_mon, dt.tm_mday, dt.tm_hour, dt.tm_min, dt.tm_sec]) \
        + bytes([1 if use_24h else 0, (dt.tm_wday + 1) % 7])  # weekday, Sunday = 0
    send_cmd(dev, payload)

set_time(open_device())  # sends current local time, 24h display
```

### Set brightness / boot animation / panel flags

```python
BRIGHTNESS = {1: 0x0f, 2: 0x4f, 3: 0xbc}

def set_brightness(dev, level: int = 2):
    send_cmd(dev, bytes([0x35, 0x01, BRIGHTNESS[level]]))

def set_boot_animation(dev, on: bool = True):
    send_cmd(dev, bytes([0x32, 0x02, 0x02 if on else 0x00, 0x02 if on else 0x00]))

def set_panel(dev, on: bool = True, show_battery: bool = True):
    flags = 0x03 if on and show_battery else (0x01 if on else 0x00)
    send_cmd(dev, bytes([0x30, 0x05, 0x04, 0x00, 0x00, flags]))
```

### Wake / resync the panel after a display-off

```python
def resync(dev, speed=3, theme=4, brightness=2, boot_animation=True):
    """Full state-resync burst (record13). The only sequence observed to
    reliably wake the panel from display-off; the flags byte alone is NOT
    enough."""
    set_panel(dev, on=True)
    send_cmd(dev, bytes([0x31, 0x02, 0x00, 0x04]))
    set_time(dev)
    set_boot_animation(dev, boot_animation)
    set_brightness(dev, brightness)
    send_cmd(dev, bytes([0x33, 0x01, speed]))
    send_cmd(dev, bytes([0x30, 0x05, 0x02, 0x00, theme]))
```

### Lid-close resync (replicate MyASUS)

```python
def on_lid_close(dev, speed=3, theme=4, brightness=2):
    set_time(dev)
    set_brightness(dev, brightness)
    send_cmd(dev, bytes([0x31, 0x02, 0x00, 0x04]))
    send_cmd(dev, bytes([0x33, 0x01, speed]))
    send_cmd(dev, bytes([0x30, 0x05, 0x02, 0x00, theme]))
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

### Push a text-template frame / stream image content

```python
def send_frame(dev, framebuffer: bytes, filter_id: int = 0x02):
    """framebuffer: 8704-byte chunk (17x512 framed, see bulk-endpoint
    section). filter_id: 0x02 image content, 0x01 text "none",
    0x03 text "news ticker"."""
    if filter_id == 0x02:
        send_cmd(dev, bytes([0x31, 0x02, 0x00, 0x04]))
    send_cmd(dev, bytes([0x30, 0x06, 0x05, 0x00, 0x00, 0x00, filter_id]))
    dev.write(IMG_EP, framebuffer)
```

## Open questions

- **`31 02 <a> <b>` value space.** Only `00 04` and `02 03` observed.
- **`f1 03` command.** Follows the time-set when clock modes are configured;
  elicits `30 31` (ASCII "01") on EP `0x82`. Purpose and reply semantics
  unknown; not sent in automatic resync bursts.
- **EP `0x82` status word** (`40 9a 10 00`, record9) — still unidentified;
  clearly context-dependent replies.
- **4bpp pixel packing** — the 17×512 framing is verified, but the
  per-pixel nibble order / pair swap is still taken from the
  `zenvision-linux` docs, not independently re-verified.
- **Brightness raw-value scale.** Levels 1–3 are `0x0f` / `0x4f` / `0xbc`
  (not linear); intermediate values and any finer granularity are untested.
- **Day-of-week bytes Wed–Sat (`03`–`06`)** — only Sun/Mon/Tue observed so
  far; the rest follows the Sunday=0 scheme but is unverified.
- **`30 05 04 00 00 <flags>` other bits** — only bits 0 (display on) and 1
  (battery) observed.

## Comparison to the original `zenvision-linux` protocol docs

What this pass confirms was **right**:
- Device identity (`0b05:8835`), interface 0 as vendor-specific/class 0xFF.
- Endpoint roles: `0x03` interrupt-OUT as the command channel, `0x07` bulk-OUT
  for framebuffer data, `0x82` interrupt-IN returning status words.
- The general shape of commands: short meaningful prefix, zero-padded to a
  512-byte buffer, `0x30`-family opcodes for apply/configure actions,
  `0x31`-family for content-mode selection.
- The autonomous/built-in-theme behavior description (MCU free-runs its own
  themes, including the clock, when nothing is actively driving the panel).
- The **8704-byte frame framing** (17 × 512-byte packets with index byte 0,
  end marker `01` at packet 16's byte 1) — now verified byte-for-byte
  against pcapng payloads.

What this pass found **wrong or incomplete**:
- **Theme selection was misattributed.** The original docs' guess of
  `33 01 IDX` as theme-select is actually the **speed** command; the real
  theme-select is `30 05 02 00 IDX`.
- **Brightness was misattributed.** The original docs put brightness in
  `31 02 BB 03`; the real brightness command is `35 01 <raw>`, with
  observed levels `0x0f` / `0x4f` / `0xbc`.
- **No time-set command was documented at all.** `40 09 ...` (the RTC/clock
  command that drives the lid-close clock animation) doesn't appear in the
  original protocol notes.
- **No clock-mode, battery-status, display-power, or boot-animation
  commands were documented** — this pass adds `30 05 01`, `30 05 04`,
  `32 02`, `35 01`, `31 02`, and the `30 06 05` apply variants.
- **The bulk endpoint was documented as a one-shot static image.** It is a
  continuous 8704-byte chunk stream for image content, and a single framed
  frame for text templates.
- **The `31 02 BB 03` "apply, brightness" framing** used by the old driver
  does not match what MyASUS sends (`31 02 00 04` / `31 02 02 03`, brightness
  separate in `35 01`).