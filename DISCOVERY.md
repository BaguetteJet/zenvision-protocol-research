# Discovery Process: Reverse-Engineering the ZenVision USB Protocol

## What it is

USBPcap is a capture driver that hooks Windows' USB stack and hands raw USB
traffic to Wireshark, the same way tcpdump/Npcap does for network packets.
Since the ZenVision panel has no public protocol docs, the only way to learn
what MyASUS is telling it is to watch the real traffic between the official
Windows app and the device, then correlate specific bytes with specific
actions taken in the app.

## How it works

- USBPcap installs as an optional component of the Wireshark Windows
  installer. It creates one virtual capture interface (`USBPcap1`,
  `USBPcap2`, …) per USB host controller/root hub on the machine.
- Windows exposes composite/internal devices (like a lid panel wired to an
  internal hub) through whichever controller they're physically attached to
  — not necessarily the first one — so the right interface has to be found
  by trial, not assumed.
- Every USB transaction on that controller is visible: enumeration
  (descriptors, `SET_ADDRESS`), and ongoing traffic tagged by bus ID, device
  address, endpoint number, and direction.
- Wireshark's USB dissector decodes the transport framing (URB type, status,
  endpoint) automatically; the actual command bytes are the payload the
  dissector labels "Leftover Capture Data" / `usb.capdata`.

## How to replicate

1. Install Wireshark with the USBPcap component checked.
2. Open Wireshark, and start captures on the `USBPcapN` interfaces one at a
   time (or several at once) until one shows live traffic — that identifies
   which root hub the target device sits on.
3. Trigger one distinctive action in the vendor app (e.g. toggle a setting)
   so there's a landmark in the capture, then check Device Manager for the
   device's VID:PID to confirm you're looking at the right hardware.
4. Find one frame that shows the device's enumeration `DEVICE DESCRIPTOR`
   (happens once per plug/boot) — it carries the `idVendor`/`idProduct`
   fields and, critically, the **bus ID** the device is on
   (`usb.bus_id`).
5. From there, work out which endpoint actually carries the interesting
   traffic — see below.

## Finding the key filter: `usb.endpoint_address.number == 3`

This filter wasn't guessed — it fell out of process of elimination:

1. **Filtering on VID/PID directly failed.** `usb.idVendor == 0x0b05 &&
   usb.idProduct == 0x8835` only matches the handful of enumeration frames
   that literally contain a `GET_DESCRIPTOR(DEVICE)` response. Regular
   command/data traffic has no VID/PID field at all — it's addressed purely
   by bus/device/endpoint — so this filter hid almost everything.
2. **Filtering on device address was fragile.** The address Windows assigns
   during enumeration (e.g. device `1`, later reassigned to something else)
   can change across sessions, so hardcoding it isn't reliable long-term.
3. **Hex-searching for known command bytes** (`Edit → Find Packet` → Packet
   bytes → Hex value) using opcodes already documented by the
   `zenvision-linux` project (`30 06 05 ...`, `31 02 ...`) located real
   traffic and, in doing so, revealed which endpoint number it was actually
   on.
4. That traffic consistently sat on **endpoint 3, OUT direction** — the
   vendor's interrupt-based command channel. Filtering on the endpoint
   *number* alone, `usb.endpoint_address.number == 3`, turned out to be the
   most stable way to isolate it: it survives address reassignment across
   capture sessions and catches every command regardless of which specific
   action triggered it, without needing to know the opcode in advance.
   Adding `&& usb.endpoint_address.direction == "OUT"` narrows it further to
   host→device only, excluding the unrelated IN-direction status reads that
   share the same endpoint number.

The general lesson: when a device has no HID/class descriptor to lean on,
identifying it by **endpoint number** rather than device address or VID/PID
is usually the most durable filter, since the endpoint layout is fixed by
the device's own descriptors and doesn't change between sessions the way
addresses do.

## From filtered capture to protocol

Once the command channel was isolated, the actual protocol discovery was
just: perform one action in the app at a time, note the wall-clock time and
what was changed, capture the resulting command burst, and diff it against
bursts from other actions (or the same action with one variable changed) to
isolate which bytes correspond to which setting. Comment-per-action logging
during capture (right-click a frame → Edit/Add Packet Comment) made this
dramatically easier than reconstructing intent after the fact.

## Capture provenance

Every command burst in `usb-packets/` was tagged at capture time with the
exact action taken in the ASUS app (MyASUS / Armoury Crate):

| Capture | What it covers |
|---|---|
| `record9` | Themes, clock modes, time-set, content apply (command channel only) |
| `record10` | Lid close behavior, brightness, continuous image streaming (EP `0x07`) |
| `record11` | Brightness levels, boot-animation toggle, display off/on |
| `record12` | Brightness level 2, full state-resync burst |
| `record13` | Display off/on with the full state-resync burst |
| `record14` | Clock modes (`f1 03` + EP `0x82` reply), Text Template filters, bulk-frame framing |
| `record15` | A Linux driver's recovery attempt (failed) — byte-identical to record13's burst |
| `record16` | Unfiltered capture of the app's successful recovery under Windows |

Records 13/15 are filtered exports; record16 is the only unfiltered one.

## The display-off latch

The full investigation that led to the CAUTION in `PROTOCOL.md`:

1. A Linux driver sent `30 05 04 00 00 00` (display off) — the panel went
   black and stayed black. The ASUS app's Display Off → On cycle (record13)
   revived it.
2. Replicating the app's cycle byte-for-byte from Linux (record15) did
   **not** revive it, even with the app's pacing (~265 ms after time-set,
   ~1.5 s before speed).
3. Also failed: flags-only on, theme commands, a USB bus reset
   (`dev.reset()`) followed by the on-burst, and pushing a white 8704-byte
   framebuffer. The `f1 03` state query shows the firmware fully alive and
   processing every command (state code tracks theme/clock/image content) —
   only the panel itself stays black. The latch even survived a Windows
   reboot (incident 1).
4. Record16 (unfiltered) shows the app's successful recovery is the *same*
   nine commands — the only extras are a `SET_IDLE` control transfer to the
   HID interface and two EP `0x84` IN polls. Neither is reproducible from
   Linux as-is: the kernel's `usbhid` driver holds the HID interface, and
   the device stalls the request otherwise.
5. NAK anomaly: in record16 the device NAK'd the app's time-set write for
   263 s and the brightness write for 1457 s before accepting them (the
   Windows stack retries interrupt-OUT indefinitely; libusb times out).
   Unconfirmed whether this patience is part of the recovery.

Conclusion: treat the display-off byte as irreversible from Linux.

## Comparison to the original `zenvision-linux` protocol docs

What this research confirms was **right**:
- Device identity (`0b05:8835`), interface 0 as vendor-specific/class 0xFF.
- Endpoint roles: `0x03` interrupt-OUT as the command channel, `0x07`
  bulk-OUT for framebuffer data, `0x82` interrupt-IN for status.
- The general command shape: short meaningful prefix, zero-padded to 512
  bytes, `0x30`-family for apply/configure, `0x31`-family for content mode.
- The MCU free-runs its own themes (including the clock) when nothing is
  actively driving the panel.
- The 8704-byte frame framing (17 × 512-byte packets, index byte 0, end
  marker `01` at packet 16's byte 1) — verified byte-for-byte against
  pcapng payloads.

What it found **wrong or incomplete**:
- **Theme selection was misattributed**: `33 01 IDX` is actually the speed
  command; the real theme-select is `30 05 02 00 IDX`.
- **Brightness was misattributed**: the docs' `31 02 BB 03` framing is not
  what MyASUS sends; brightness is a separate `35 01 <raw>` command with
  observed levels `0x0f` / `0x4f` / `0xbc`.
- **No time-set command documented**: `40 09 …` (drives the lid-close
  clock) was missing entirely.
- **No clock-mode, battery, display-power, or boot-animation commands**:
  this research adds `30 05 01`, `30 05 04`, `32 02`, `35 01`, `31 02`,
  and the `30 06 05` apply variants.
- **The bulk endpoint was documented as a one-shot image**: it is a
  continuous 8704-byte chunk stream for image content, and a single framed
  frame for text templates.

## Open questions

- **The display-off latch** — see above. The app's recovery adds only
  `SET_IDLE` + HID polls + multi-minute NAK patience, none reproducible
  from Linux as-is.
- **`31 02 <a> <b>` value space** — only `00 04` and `02 03` observed.
- **`f1 03` reply semantics** — the rest of the 512-byte reply is zero;
  unknown if other query IDs exist.
- **4bpp pixel packing** — the 17×512 framing is verified, but the
  per-pixel nibble order / pair swap is still taken from the
  `zenvision-linux` docs, not independently re-verified against a rendered
  capture.
- **Brightness raw-value scale** — levels 1–3 are `0x0f` / `0x4f` / `0xbc`
  (not linear); intermediate values untested.
- **Day-of-week bytes Wed–Sat (`03`–`06`)** — only Sun/Mon/Tue observed;
  the rest follows the Sunday=0 scheme but is unverified.
- **`30 05 04` other bits** — only bits 0 and 1 observed; the byte does
  not affect the `f1 03` state code.