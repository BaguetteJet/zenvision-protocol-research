# zenvision-protocol

Protocol derived from USB packet captures on Windows via USBPcap, watching the MyASUS app was communicate with the panel.

> [!IMPORTANT]   
> Developed independently from [zenvision-linux](https://github.com/tarpediem/zenvision-linux), which was the first open-source project to document this protocol by decompiling the MyASUS app using Ghidra.  

See [PROTOCOL.md](/PROTOCOL.md) for detailed breakdown.

## Get Started

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install pyusb
```

```bash
python3 zenvision.py
```