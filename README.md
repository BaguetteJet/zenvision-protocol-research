# zenvision-protocol-research

USB protocol to communicate with the ZenVision display built into the lid of the ASUS ZenBook 14X OLED Space Edition (UX5401ZAS).

The protocol was derived from USB packet captures on Windows via USBPcap, watching the MyASUS app was communicate with the panel. Tested and replicated using python on linux.

> [!IMPORTANT]   
> Developed independently from [zenvision-linux](https://github.com/tarpediem/zenvision-linux), which was the first open-source project to document parts of this protocol by decompiling the MyASUS app using Ghidra. This research confirms some of its findings, corrects or disproves others, and documents additional commands and protocol behavior that were previously unknown.

## Reverse-Engineered Commands

Commands sent to device `0b05:8835`, Interface `0`, endpoint `0x03`, zero padded to 512-bytes.

| Command                       | Description         | Values                                                       |
| :---------------------------- | :------------------ | :----------------------------------------------------------- |
| `30 05 01 <a>`                | Set clock layout    | `01`-`02` Time mode 1-2                                      |
| `30 05 02 00 <a>`             | Set built-in theme  | `01`-`04` Theme 1-4                                          |
| `30 05 04 00 00 00 <a>`       | Set power           | `00` Off, `01` On, `03` On + battery icon                    |
| `30 06 05 00 00 00 00 <a>`    | Set content mode    | `01` Image, `02` Stream, `03` News ticker                    |
| `31 02 <a> <b>`               | Set screen sweep    | `00 04` Off, `02 03` On                                      |
| `32 02 <a> <b>`               | Set boot animation  | `02 02` On, `00 00` Off                                      |
| `33 01 <a>`                   | Set animation speed | `01` Slow, `02` Medium, `03` Fast                            |
| `35 01 <a>`                   | Set brightness      | `0F` Dim, `4F` Medium, `BC` Bright, `00`-`FF` Custom         |
| `40 09 <a> <b> <c> ... <i>`   | Set clock date/time | Year, month, day, hour, minute, second, format, weekday      |
| `F1 03`                       | Query content state | Return `01` Clock, `02` Theme, `07` Image                    |


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
