# ASUS ZenVision (UX5401ZAS) — USB Protocol

Device: `0b05:8835` (Nuvoton M480, "M480 BULK"), interface 0, vendor-specific class (0xFF).

## Endpoints

| Endpoint | Direction | Type | Role |
|---|---|---|---|
| `0x03` | OUT | Interrupt, 512B | **Command channel** — every command below |
| `0x07` | OUT | Bulk | Framebuffer data — 8704-byte frames, see [Sending frames](#sending-frames-ep-0x07) |
| `0x82` | IN | Interrupt | Identity string (`AS-AOLED.13.000,<serial>,<serial>`) and `f1 03` query replies |

No kernel driver binds the vendor interface; the panel is driven entirely by
these two endpoints.

## Command framing

Every command is a **512-byte** interrupt-OUT transfer on EP `0x03`. Only
the leading bytes shown below carry meaning — everything after them is
`0x00` padding. This applies to every command in this document.

## Commands

### `33 01 <speed>` — animation speed
```
33 01 01   speed 1
33 01 02   speed 2
33 01 03   speed 3
```
Animation speed of themes and clock animations.

### `35 01 <brightness>` — brightness level
```
35 01 0F   level 1
35 01 4F   level 2
35 01 BC   level 3
```
Brightness of themes and clock animations. Raw byte values, not linear. *(only these three levels are known)*

### `32 02 <a> <b>` — boot-animation toggle
```
32 02 02 02   boot animation ON
32 02 00 00   boot animation OFF
```

### `30 05 02 00 <idx>` — select built-in theme
```
30 05 02 00 01   Theme 1
30 05 02 00 02   Theme 2
30 05 02 00 03   Theme 3
30 05 02 00 04   Theme 4
```
Sent immediately after `33 01 <speed>`. The display runs the theme autonomously once selected.

### `30 05 01 <mode>` — select clock layout
```
30 05 01 01   Time mode 1
30 05 01 02   Time mode 2
```
Followed by `33 01 <speed>` and `40 09` time-set commands.

### `30 05 04 00 00 <flags>` — panel flags

| Flags | Meaning |
|---|---|
| `03` | display ON, battery shown |
| `01` | display ON, battery hidden |
| `00` | display OFF |

The battery icon is only visible in in the clock layout `Time mode 1` and the lid close animation.

> [!CAUTION]   
> **Never send `30 05 04 00 00 00` (display OFF).** It latches the panel
> black in a way no Linux-side command has ever reversed — not the on flags,
> not theme commands, not a byte-identical copy of the ASUS app's recovery
> burst, not a USB reset, not a Windows reboot. Only the ASUS app itself
> (Windows) has revived it, and the mechanism is unknown. `zenvision.py`
> refuses to send this command; treat the display-off byte as irreversible.
> Details in [DISCOVERY.md](DISCOVERY.md#the-display-off-latch).

### `40 09 <date/time>` — set clock time

| Byte(s) | Field | Encoding |
|---|---|---|
| 0 | opcode | `0x40` |
| 1 | sub-type marker | constant `0x09` |
| 2–3 | year | little-endian u16 (2026 → `ea 07`) |
| 4 | month | binary, 1–12 |
| 5 | day | binary, 1–31 |
| 6 | hour | binary, 0–23, always stored 24h |
| 7 | minute | binary, 0–59 |
| 8 | second | binary, 0–59 |
| 9 | display format | `1` = 24h, `0` = 12h |
| 10 | day of week | `0` = Sunday … `6` = Saturday |
| 11–511 | padding | zero |

All fields are **local wall-clock time** (not UTC, not epoch). The 12h/24h
toggle only changes byte 9 — the stored hour is always 24h binary.

Worked examples (zero-padded to 512 bytes):
```
40 09 EA 07 09 0F 0E 1E 00 01 02   Sep 15 2026 (Tue) 14:30:00, 24h
40 09 EA 07 0C 19 08 05 1E 00 01 05   Dec 25 2026 (Fri) 08:05:30, 12h
```

### `f1 03` — content-engine state query

```
f1 03   →   EP 0x82 replies with a 512-byte buffer
```

The reply's leading bytes are an ASCII state code:

| Reply | Content engine |
|---|---|
| `01` | clock mode (`30 05 01`) |
| `02` | built-in theme (`30 05 02`) |
| `07` | image-backed content (bulk stream) |

Read-only — other `f1 <x>` variants reply with the same code.

### `31 02 <a> <b>` — select content-engine mode
```
31 02 00 04   image-backed content (custom images, personal labels)
31 02 02 03   procedurally-rendered content (clock mode 2, text templates)
```
Sent before the matching `30 06 05` apply. Also used as a generic resync
prelude before theme/clock commands.

### `30 06 05 00 00 00 <val>` — apply/commit content
```
30 06 05 00 00 00 02   image-backed content (constant for all images)
30 06 05 00 00 00 03   Text Template, filter "news ticker"
30 06 05 00 00 00 01   Text Template, filter "none"
```
For images the byte is constant — the visual filter lives in the streamed
pixels, not here. For text templates the filter is device-side: `01` plays a
horizontal-line wipe ("cleans" the screen), `03` scrolls the text.

## Observed sequences per app action

| App action | Command sequence |
|---|---|
| Pick Theme N, speed S | `33 01 <S>` → `30 05 02 00 <N>` |
| Set brightness level B | `35 01 <raw(B)>` |
| Toggle boot animation | `32 02 02 02` / `32 02 00 00` |
| Display on (recovery) | `30 05 04 00 00 03` → `31 02 00 04` → `40 09 …` → `32 02 02 02` → `35 01 …` → `33 01 …` → `30 05 02 00 …` |
| Time Mode 1 | `30 05 04 00 00 <flags>` → `33 01 <S>` → `30 05 01 01` → `40 09 …` → `f1 03` |
| Time Mode 2 | `31 02 02 03` → `30 05 01 02` → `40 09 …` → `f1 03` |
| Apply image / personal label | `31 02 00 04` → `30 06 05 00 00 00 02` → (continuous frame stream) |
| Apply Text Template, filter F | `31 02 00 04` (or `31 02 02 03`) → `30 06 05 00 00 00 <F>` → one frame → `33 01 <S>` |
| **Lid close** | `40 09 …` → `35 01 …` → `31 02 00 04` → `33 01 …` → `30 05 02 00 …` |

## Lid-close behavior

When the lid closes, MyASUS waits ~9 s, then pushes one state-resync burst
(current local time + brightness + content-mode prelude + speed + theme),
and nothing at reopen. The lid clock is therefore driven by that single
one-shot burst, not by continuous time updates:

```
40 09 EA 07 09 0F 12 01 13 01 02   time-set (current local time + weekday)
35 01 4F                           brightness
31 02 00 04                        content-mode prelude
33 01 03                           speed
30 05 02 00 04                     theme
```

A Linux driver should hook the lid-close event and push this burst right
before the display sleeps.

## Sending frames (EP `0x07`)

Every bulk chunk is an **8704-byte frame** of **17 × 512-byte packets**:

| Packet byte(s) | Meaning |
|---|---|
| byte 0 | packet index `0x00`–`0x10` |
| byte 1 | `0x00`, except packet 16: `0x01` (end marker) |
| bytes 2–3 | reserved, `0x00` |
| bytes 4–511 | payload (508 bytes per packet) |

Concatenating packets 0–15 (16 × 508 = 8128 bytes) plus the first 64
payload bytes of packet 16 yields the **8192-byte 4bpp framebuffer**
(256×64, row-major, two 4-bit gray pixels per byte). The exact nibble order
within the bytes is still unverified against a rendered capture.

How frames are sent depends on the content:

- **Image content**: a continuous stream of frames (~60–70 ms apart, ~15
  fps) for as long as the content stays active — filters are live
  animations rendered into the pixels.
- **Text templates**: a single frame per apply; the filter animation is
  device-side.

```python
def send_frame(dev, framebuffer: bytes, filter_id: int = 0x02):
    """framebuffer: 8704-byte framed frame (see table above).
    filter_id: 0x02 image content, 0x01 text "none", 0x03 text "news ticker"."""
    if filter_id == 0x02:
        send_cmd(dev, bytes([0x31, 0x02, 0x00, 0x04]))
    send_cmd(dev, bytes([0x30, 0x06, 0x05, 0x00, 0x00, 0x00, filter_id]))
    dev.write(IMG_EP, framebuffer)
```

## Python driver

`zenvision.py` is the reference implementation (pyusb/libusb): `open_device`,
`send_cmd` (zero-padding + timeout retry), one function per command, a
paced `resync()` state burst, and a safe `__main__` (state query + time-set
+ theme). Run it with the repo's virtualenv:

```bash
source .venv/bin/activate
python zenvision.py
```

Pacing notes for implementers: the app does **not** slam bursts out
back-to-back. It pauses ~265 ms after the time-set and ~1.5 s before the
speed command (the device is busy committing the clock — unslowed bursts
time out). `resync()` in `zenvision.py` mirrors this pacing.