# zenvision-protocol-research

USB protocol to communicate with the ZenVision display built into the lid of the ASUS ZenBook 14X OLED Space Edition (UX5401ZAS).

The protocol was derived from USB packet captures on Windows via USBPcap, watching the MyASUS app was communicate with the panel. Tested and replicated using python on linux.

> [!IMPORTANT]   
> Developed independently from [zenvision-linux](https://github.com/tarpediem/zenvision-linux), which was the first open-source project to document parts of this protocol by decompiling the MyASUS app using Ghidra. This research confirms some of its findings, corrects or disproves others, and documents additional commands and protocol behavior that were previously unknown.

See [PROTOCOL.md](/PROTOCOL.md) for a detailed commands breakdown and [DISCOVERY.md](/DISCOVERY.md) for the discovery process.

## Get Started

Set up virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install pyusb
```

Review commands available in [zenvision.py](/zenvision.py)

Edit and run script
```bash
python3 zenvision.py
```

## Image Data

My script does not cover image encoding and streaming. See tarpediem's project [zenvision-linux](https://github.com/tarpediem/zenvision-linux).
