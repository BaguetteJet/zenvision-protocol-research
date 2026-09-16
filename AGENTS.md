# AGENTS.md

Guidance for AI agents and contributors working in this repository.

## Project

Reverse-engineering of the ASUS ZenVision lid OLED panel USB protocol
(ASUS Zenbook 14X OLED Space Edition, UX5401ZAS; device `0b05:8835`,
Nuvoton M480 "M480 BULK"). The goal is a Linux userspace driver.

- `PROTOCOL.md` — the protocol spec (command reference, frame formats,
  observed app sequences). Keep it concise and implementation-focused.
- `DISCOVERY.md` — how the protocol was reverse-engineered: capture
  workflow, record provenance, open questions, and the display-off latch
  investigation. Research narrative and open questions live here, not in
  PROTOCOL.md.
- `zenvision.py` — the reference driver (pyusb/libusb). Keep it simple and
  clean; one function per command, comments in the `# xx yy <param> - ...`
  style.
- `usb-packets/` — USBPcap/Wireshark captures (`.txt` exports and
  `.pcapng`). `notes/` — AI analysis notes.
- `OLD-RESEARCH/` — a previous researcher's (partially incorrect) work;
  kept for reference, do not treat as authoritative.

## Critical rules

- **NEVER send `30 05 04 00 00 00` (display off).** It latches the panel
  black irreversibly from Linux; only the ASUS app under Windows has ever
  revived it. `set_panel()` asserts `on=True` by design — do not remove or
  bypass that guard. Any new code path that could produce this byte must be
  blocked with a reference to PROTOCOL.md's CAUTION.
- Do not invent protocol commands from the OLD-RESEARCH docs — verify
  against PROTOCOL.md (which was derived from tagged captures) first.
- Keep the CAUTION in PROTOCOL.md GitHub-style (`> [!CAUTION]`).

## Environment

- Python venv at `.venv/` (pyusb installed). Use `.venv/bin/python`.
- No lint/typecheck configured; verify with
  `.venv/bin/python -m py_compile <file>`.
- The device may be attached on this machine (see `lsusb`); tests that
  touch the live device must be safe — never send the display-off byte.

## Conventions

- Commands are 512-byte interrupt-OUT transfers on EP `0x03`, zero-padded;
  only the leading bytes carry meaning.
- Framebuffer frames on EP `0x07` are 8704 bytes = 17 × 512-byte packets
  (byte 0 = packet index `0x00`–`0x10`, packet 16 byte 1 = `0x01` end
  marker, bytes 2–3 reserved, bytes 4–511 payload).
- Time fields are local wall-clock time; weekday byte is Sunday = 0.
- The app paces its bursts (~265 ms after time-set, ~1.5 s before speed);
  unslowed bursts cause `USBTimeoutError`. `send_cmd` retries on timeout.