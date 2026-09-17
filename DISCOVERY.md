# Discovery Process

## How it works

- USBPcap hooks Windows' USB stack and hands raw USB traffic to Wireshark. It creates one virtual interface (`USBPcapN`) per root hub; the panel sits on whichever hub it's wired to, found by trial (`USBPcap2` here), confirmed via the enumeration frame's `usb.bus_id`.
- Wireshark's USB dissector handles the transport framing; the actual command bytes are the "Leftover Capture Data" / `usb.capdata` payload.
- Commands are zero-padded 512-byte writes to endpoint `0x03` (interrupt OUT), framebuffers go to `0x07` (bulk OUT), replies come back on `0x82` (interrupt IN). See [PROTOCOL.md](/PROTOCOL.md).

## Isolating the command channel

- **VID/PID filters don't work.** `usb.idVendor`/`usb.idProduct` only appear in the handful of `GET_DESCRIPTOR(DEVICE)` enumeration frames; regular command traffic carries neither.
- **Device address is fragile.** Windows reassigns `usb.device_address.number` between sessions.
- **Endpoint number is durable.** Hex-searching for opcodes from the `zenvision-linux` project revealed the command channel sat on endpoint 3, OUT. Endpoint layout is fixed by the device's own descriptors and never changes, so the filter used for all captures is `usb.endpoint_address.number == 3 && usb.endpoint_address.direction == "OUT"`.
- Ended up using `usb.device_address==1`

## From capture to protocol

Perform one action in the app at a time, note the wall-clock time and what changed, capture the resulting burst, and diff bursts (or the same burst with one variable changed) to isolate which bytes correspond to which setting. Tagging frames with packet comments at capture time made this dramatically easier.

## Capture provenance

Records 1-8 were trial runs. The filter used is in the filename; record16 is the only unfiltered capture. See [usb-packets/README.md](/usb-packets/README.md).

| Capture | What it covers |
|---|---|
| `record9` | themes, speeds, clocks, filters, text templates, personal labels (no settings menu) |
| `record10` | lid close behavior, brightness, continuous image streaming (EP `0x07`) |
| `record11` | settings menu: brightness levels 1 and 3, boot-animation toggle, display off/on |
| `record12` | brightness level 2 |
| `record13` | display off/on |
| `record14` | clock modes (`f1 03` + EP `0x82` reply), text-template filters, bulk-frame framing |
| `record15` | successful recovery (full settings sequence) |
| `record16` | unfiltered capture of the app's successful recovery |
| `record17` | battery setting and display on/off |

## Recovery

An unrecognised command can leave the panel black; the full settings sequence revives it (see PROTOCOL.md > Recovery). This was the subject of a long investigation: after the display-off latch (records 13-15) seemed unrecoverable from Linux. Discovered that show battery icon recovers display.

## Comparison to [zenvision-linux](https://github.com/tarpediem/zenvision-linux)

**Confirmed right:** device identity (`0b05:8835`), endpoint roles, 512-byte zero-padded command framing, `0x30`-family apply / `0x31`-family content commands, the panel's autonomous themes, and the 8704-byte bulk-frame framing.

**Wrong or incomplete:** theme-select is `30 05 02 00 <idx>`, not `33 01` (that's speed); brightness is `35 01 <raw>`, not `31 02`. Time-set, clock mode, power, battery icon, boot animation, and screen sweep were undocumented.

## Open questions

- `31 02 <a> <b>` value space only `00 04` (off) and `02 03` (on) observed.
- `f1 03` reply only codes 01 (clock), 02 (theme), 07 (image) known; unknown if other query IDs exist.
- Brightness raw-value scale? levels 1-3 are `0x0f`/`0x4f`/`0xbc` (not linear); intermediates untested.
- Settings sequence, whether the theme command is replaced when non-built-in content is displayed (see PROTOCOL.md ⭐).