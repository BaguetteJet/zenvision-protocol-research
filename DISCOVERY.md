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