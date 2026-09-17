# ZenVision Protocol

USB protocol to communicate with the ZenVision display built into the lid of the ASUS ZenBook 14X OLED Space Edition (UX5401ZAS).

The ZenVision display is a 256 x 64 pixels, monochrome, 4-bit grayscale (16 levels) OLED panel.

Device `0b05:8835`, Interface `0`, vendor-specific class (0xFF). No kernel driver binds it.

> [!NOTE]   
> The protocol is derived from USB packet captures on Windows via USBPcap, watching the MyASUS app was communicate with the panel. See raw capture records in [/usb-packets](/usb-packets/) and process details in [DISCOVERY.md](/DISCOVERY.md).

## Endpoints

| Endpoint | Direction | Type | Size | Role |
|---|---|---|---|---|
| `0x03` | OUT | Interrupt | 512 bytes | Commands  |
| `0x07` | OUT | Bulk | 8704 bytes | Framebuffer |
| `0x82` | IN | Interrupt | 18 bytes | Reponse |
 
## Commands
***Endpoint 0x03*** - Interrupt OUT   
Leading bytes contain the command, 512-byte zero-padded. 

Sample MyASUS sequences containing each command listed as bullet points.

### `30 05 01 <mode>` set clock layout
```
30 05 01 01   time mode 1
30 05 01 02   time mode 2
```
- power on > **time mode 1** > speed > datetime
- screen sweep on > **time mode 2** > speed > datetime

The panel runs clock layout autonomously.

### `30 05 02 00 <theme>` set built-in theme
```
30 05 02 00 01   theme 1
30 05 02 00 02   theme 2
30 05 02 00 03   theme 3
30 05 02 00 04   theme 4
```
- speed > **theme**

The panel runs the theme autonomously.

### `30 05 04 00 00 00 <val>` set power
```
30 05 04 00 00 00 00   power off
30 05 04 00 00 00 01   power on, battery icon off
30 05 04 00 00 00 03   power on, battery icon on
```
- **power off** > screen sweep off
- **power on** > time mode 1 > speed > datetime

Battery icon only visible in Time mode 1 and during the lid close animation.

### `30 06 05 00 00 00 00 <mode>` set content mode
```
30 06 05 00 00 00 00 01   content mode 1 - filter "none"
30 06 05 00 00 00 00 02   content mode 2 - 
30 06 05 00 00 00 00 03   content mode 3 - filter "news ticker"
```
- screen sweep off > **content mode 3** > speed

⭐ **TO BE CONFIRMED**

### `31 02 <a> <b>` set screen sweep
```
31 02 00 04   screen sweep off
31 02 02 03   screen sweep on
```
- power off > **screen sweep off**
- **screen sweep off** > content mode 3 > speed
- **screen sweep on** > time mode 2 > speed > datetime
- content mode 1 > **screen sweep on**

"Screen sweep" is an animation of horizontal bars sweeping across the screen. It interrupts certain currently playing built-in content every few seconds. Only observed for time mode 2 and text template set to filter "none" (content mode 1). Presumably intented to reduce OLED burn-in risk with static content.

### `32 02 <a> <b>` set boot animation
```
32 02 02 02   boot animation on
32 02 00 00   boot animation off
```
- part of [settings sequence](#settings-sequence)

### `33 01 <speed>` set animation speed
```
33 01 01   speed 1 slow
33 01 02   speed 2
33 01 03   speed 3 fast
```
- **speed** > theme
- screen sweep off > content mode 3 > **speed**
- power on > time mode 1 > **speed** > datetime
- screen sweep on > time mode 2 > **speed** > datetime

Applies only to built-in content (theme, clock, animations).

### `35 01 <val>` set brightness
```
35 01 0F   brightness 1 dim
35 01 4F   brightness 2 
35 01 BC   brightness 3 bright

35 01 00-FF  custom brightness 0-255
```
- part of [settings sequence](#settings-sequence)

Applies only to built-in content (theme, clock, animations). Only three levels used by MyASUS app. Custom values 0-255 (`00`-`FF`) work.

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

```
40 09 EA 07 09 0F 0E 1E 00 01 02   2026 Sep 15 14:30:00 24h Tue
40 09 EA 07 0C 19 08 05 1E 00 05   2026 Dec 25 08:05:30 12h Fri
```
- power on > **time mode 1** > speed > datetime
- screen sweep on > **time mode 2** > speed > datetime

Time displayed on the lid close animation and both time modes.

### `F1 03` query content state
```
F1 03
```
**Endpoint 0x82** replies with a 512-byte ASCII status code:

| Reply | Content engine |
|---|---|
| `01` | clock mode |
| `02` | built-in theme |
| `07` | image content |

⭐ **TO BE CONFIRMED**

## Framebuffer

***Endpoint 0x07*** - Bulk OUT    
One frame is a single 8704-byte bulk transfer. No commands. This endpoint carries pixel data only.

| Byte(s) | Meaning |
|---|---|
| byte 0 | packet index, 0-16 |
| byte 1 | `0x00`, except packet 16: `0x01` (end marker) |
| bytes 2-3 | zero |
| bytes 4-511 | payload |

The concatenated payload is **8192 bytes total**, matching a 256×64 4-bit-grayscale framebuffer (2 packed pixels/byte). Packets 0-15 are full (16 × 508 = 8128 bytes); the remaining 64 bytes land in packet 16, whose payload area is padded out to 512.

- **Static content**: Single chunk per apply. (MyASUS text templates)
- **Streamed content**: Streamed continuously for as long as it's active. Filters are live animations in the pixel data. (MyASUS custom theme, personal label)

⭐ **TO BE CONFIRMED**

## Settings Sequence
Any settings change in the MyASUS Exclusives settings menu triggers the following seven-command burst, with just one value changed. Every field is resent at its current value:

```
30 05 04 00 00 00 <val>   power on/off
31 02 00 04               screen sweep off
40 09 <time> ...          datetime, format, weekday
32 02 <a> <b>             boot animation on/off
35 01 <val>               brightness level
33 01 <speed>             speed
30 05 02 00 <theme>       theme
```

⭐ **TO BE CONFIRMED** if other content form displayed, is theme command replaced?

## Recovery

If an unrecognised command is sent, the screen goes black and won't even show lid animation. To recover, run full [settings sequence](#settings-sequence).