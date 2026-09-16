# ZenVision Protocol

USB protocol to communicate with the ZenVision display built into the lid of the ASUS ZenBook 14X OLED Space Edition (UX5401ZAS)

ZenVision is a 256 × 64 pixels, monochrome, 4-bit grayscale (16 levels) OLED panel.

Device `0b05:8835`, Interface `0`, vendor-specific class (0xFF). No kernel driver binds it.

> [!NOTE]   
> Protocol derived from USB packet captures on Windows via USBPcap, watching the MyASUS app talk to the panel. See raw capture records in [/usb-packets](/usb-packets/). Process details in [DISCOVERY.md](/DISCOVERY.md).

## Endpoints

| Endpoint | Direction | Type | Size | Role |
|---|---|---|---|---|
| `0x03` | OUT | Interrupt | 512 bytes | Commands  |
| `0x07` | OUT | Bulk | 8704 bytes | Framebuffer (17 x 512-byte packets)|
| `0x82` | IN | Interrupt | 18 bytes | Status |
 
## Commands
***Endpoint 0x03*** - Interrupt OUT   
Leading bytes contain the command, 512-byte zero-padded. 

### `30 05 01 <mode>` set clock layout
```
30 05 01 01   time mode 1
30 05 01 02   time mode 2
```
The panel runs the clock layout autonomously. Followed by **speed** and **datetime**.

### `30 05 02 00 <theme>` set built-in theme
```
30 05 02 00 01   theme 1
30 05 02 00 02   theme 2
30 05 02 00 03   theme 3
30 05 02 00 04   theme 4
```
Sent after **speed**. The panel runs the theme autonomously.

### `30 05 04 00 00 <flags>` set panel state
```
30 05 04 00 00 03   Display On, battery shown
30 05 04 00 00 01   Display On, battery hidden
30 05 04 00 00 00   Display Off
```

> [!CAUTION]   
> **Sending `30 05 04 00 00 00` (Display Off) has not been reliably recoverable from Linux.** Every capture showing successful recovery was taken on Windows, where the panel does come back. Replicating that same recovery burst from a Linux implementation has consistently **failed** to turn the display back on. The cause is unresolved. Possibly a missing precursor command, pacing/timing sensitivity, or something specific to how libusb/the kernel handles this device versus the Windows driver stack. **Treat this command as high-risk on Linux until a working recovery path is confirmed.**

### `30 06 05 00 00 00 <val>` apply/commit content
```
30 06 05 00 00 00 01   Text Template, filter "none"
30 06 05 00 00 00 02   image-backed content (constant regardless of filter)
30 06 05 00 00 00 03   Text Template, filter "news ticker"
```
Text Templates also push a real framebuffer over EP `0x07` (confirmed) —
so this isn't "device renders text, image renders pixels"; everything is
pixel-pushed. What the filter actually looks like on-panel is unverified —
no visual confirmation, only command bytes.

### `31 02 <a> <b>` unknown
```
31 02 00 04   seen before/after nearly every action
31 02 02 03   seen for Time Mode 2 and Text Template filter "none"
```
Position in sequence isn't fixed. Real purpose unresolved.

### `32 02 <a> <b>` set boot animation
```
32 02 02 02   boot animation on
32 02 00 00   boot animation off
```

### `33 01 <speed>` set animation speed
```
33 01 01   speed 1 slow
33 01 02   speed 2
33 01 03   speed 3 fast
```
Applies only to built-in content (theme, clock).

### `35 01 <val>` set brightness
```
35 01 0F   brightness 1 dim
35 01 4F   brightness 2 
35 01 BC   brightness 3 bright
```
Applies only to built-in content (theme, clock). Only these three levels are known.

### `40 09 <time>` set clock time

| Byte(s) | Field | Encoding | Example
|---|---|---|---|
| 0-1 | command | 0x40 0x09 | `40 09` |
| 2-3 | year | little-endian u16 | `EA 07` 2026 |
| 4 | month | binary, 1-12 | `09` September | 
| 5 | day | binary, 1-31 | `0F` 15th |
| 6 | hour | binary, 0-23, always stored 24h | `0E` 14 hour | 
| 7 | minute | binary, 0-59 | `1E` 30 minute |
| 8 | second | binary, 0-59 | `00` 0 second |
| 9 | format | 1 = 24h, 0 = 12h | `01` 24h |
| 10 | weekday | 0 = Sunday … 6 = Saturday | `05` friday |

Time displayed on the lid close animation and both time modes.

```
40 09 EA 07 09 0F 0E 1E 00 01 02   Sep 15 2026 (Tue) 14:30:00, 24h
40 09 EA 07 0C 19 08 05 1E 00 05   Dec 25 2026 (Fri) 08:05:30, 12h
```

### `F1 03` request content state
```
F1 03
```
**Endpoint 0x82** replies with a 512-byte status code:

| Reply | Content engine |
|---|---|
| `01` | clock mode |
| `02` | built-in theme |
| `07` | image content |

In the Time Mode 1/2 setup sequence it's sent once, right after `40 09`, with roughly a 1.5s pause beforehand. Sending it immediately risks a timeout.

## Framebuffer

***Endpoint 0x07*** interrupt-OUT    
512-byte zero-padded interrupt-OUT transfer. Leading bytes contain the command.

Confirmed by direct inspection of a captured bulk payload: each 8704-byte
transfer is 17 sub-packets of 512 bytes each.

| Byte(s) | Meaning |
|---|---|
| byte 0 | packet index, 0-16 |
| byte 1 | `0x00`, except packet 16: `0x01` (end marker) |
| bytes 2-3 | zero |
| bytes 4-511 | payload |

**8192 bytes total**, matching a 256×64 4-bit-grayscale
framebuffer (2 packed pixels/byte).

- **Static content**: Single chunk per apply. (MyASUS text templates)
- **Streamed content**: Streamed continuously for as long as it's active. Filters are live animations in the pixel data. (MyASUS custom theme, personal label)

```python
def send_frame(dev, framebuffer: bytes, filter_id: int = 0x02):
    """framebuffer: pre-framed 8704-byte payload (see table above).
    filter_id: 0x02 image content, 0x01/0x03 text template filters."""
    send_cmd(dev, bytes([0x31, 0x02, 0x00, 0x04]))
    send_cmd(dev, bytes([0x30, 0x06, 0x05, 0x00, 0x00, 0x00, filter_id]))
    dev.write(IMG_EP, framebuffer)
```

## Settings Change Sequence

Sequence of commands sent after any setting changes in the MyASUS Exclusives settings menu. 

Display On, brightness, boot animation, all trigger the seven-command burst, with just one value changed. Every field is resent at its current value, not only the one that changed:

```
30 05 04 00 00 <flags>    panel state
31 02 00 04               unknown
40 09 <time>              datetime, format, weekday
32 02 <a> <b>             boot animation
35 01 <val>               brightness
33 01 <speed>             speed
30 05 02 00 <theme>       theme
```

## Observed sequences

| App action | Command sequence |
|---|---|
| Display Off | `30 05 04 00 00 00` > `31 02 00 04` |
| Display On | full settings sequence (see above) |
| Set brightness | full settings sequence (see above) |
| Boot animation Off  | full settings sequence (see above) |
| Boot animation On | full settings sequence (see above) |
| Theme 1-4 | `33 01 <S>` > `30 05 02 00 <N>` |
| Time Mode 1 | `30 05 04 00 00 <flags>` > `33 01 <S>` > `30 05 01 01` > `40 09 <time>` > `F1 03` > response |
| Time Mode 2 | `31 02 02 03` > `30 05 01 02` > `40 09 <time>` > `F1 03` > response |
| Apply image or personal label | `31 02 00 04` > `30 06 05 00 00 00 02` > continuous frame stream |
| Apply text template with filter | `31 02 00 04` or `31 02 02 03` > `30 06 05 00 00 00 <F>` > one frame → `33 01 <S>` |

Theme N, Speed S, Filter F

## Open questions

- `31 02 <a> <b>` purpose unknown.
- Endpoint 0x82 18-byte telemetry. 
- How to recover display after **Display Off** on Linux, see the caution above.