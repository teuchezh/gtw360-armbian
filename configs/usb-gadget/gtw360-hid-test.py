#!/usr/bin/env python3
"""Create a test keyboard and mouse. This tool never sends input reports."""
import argparse
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stop', action='store_true')
args = parser.parse_args()
gadget = Path('/sys/kernel/config/usb_gadget/gtw360-hid-test')
controllers = [u.name for u in Path('/sys/class/udc').glob('*')
               if '2184000.usb' in str((u / 'device').resolve())]
udc = controllers[0] if len(controllers) == 1 else ''
if args.stop:
    if (gadget / 'UDC').exists():
        (gadget / 'UDC').write_text('\n')
    print('Test gadget unbound')
    raise SystemExit(0)
if not Path('/sys/class/udc', udc).exists():
    raise SystemExit('USB0 must boot in peripheral mode first')
for module in ['libcomposite', 'usb_f_hid']:
    subprocess.run(['modprobe', module], check=True)
if subprocess.run(['mountpoint', '-q', '/sys/kernel/config']).returncode:
    subprocess.run(['mount', '-t', 'configfs', 'configfs', '/sys/kernel/config'], check=True)
root = gadget.parent
for other in root.glob('*/UDC'):
    if other.parent != gadget and other.read_text().strip() == udc:
        raise SystemExit('UDC is already used by another gadget')
if not (gadget / 'UDC').exists() or not (gadget / 'UDC').read_text().strip():
    gadget.mkdir(exist_ok=True)
    for name, value in [('idVendor', '0x1d6b'), ('idProduct', '0x0104'),
                        ('bcdDevice', '0x0100'), ('bcdUSB', '0x0200'),
                        ('bDeviceClass', '0'), ('bDeviceSubClass', '0'), ('bDeviceProtocol', '0')]:
        (gadget / name).write_text(value)
    strings = gadget / 'strings/0x409'
    strings.mkdir(exist_ok=True)
    for name, value in [('serialnumber', 'GTW360-HID-TEST'), ('manufacturer', 'GTW360 project'),
                        ('product', 'GTW360 test keyboard and mouse')]:
        (strings / name).write_text(value)
    config = gadget / 'configs/c.1'
    config.mkdir(exist_ok=True)
    (config / 'bmAttributes').write_text('0xC0')
    (config / 'MaxPower').write_text('0')
    (config / 'strings/0x409').mkdir(exist_ok=True)
    (config / 'strings/0x409/configuration').write_text('HID keyboard and mouse')
    keyboard = bytes.fromhex('05010906a101050719e029e71500250175019508810295017508810395057501050819012905910295017503910395067508150025650507190029658100c0')
    mouse = bytes.fromhex('05010902a1010901a100050919012903150025019503750181029501750581010501093009311581257f750895028106c0c0')
    for name, protocol, length, descriptor in [('hid.keyboard', 1, 8, keyboard), ('hid.mouse', 2, 3, mouse)]:
        function = gadget / 'functions' / name
        function.mkdir(exist_ok=True)
        for attribute, value in [('protocol', protocol), ('subclass', 1), ('report_length', length)]:
            (function / attribute).write_text(str(value))
        (function / 'report_desc').write_bytes(descriptor)
        if name == 'hid.mouse' and (function / 'no_out_endpoint').exists():
            (function / 'no_out_endpoint').write_text('1')
        link = config / name
        if not link.is_symlink():
            link.symlink_to(function)
    (gadget / 'UDC').write_text(udc)
print(json.dumps({'udc': (gadget / 'UDC').read_text().strip(),
                  'state': Path('/sys/class/udc', udc, 'state').read_text().strip(),
                  'keyboard': Path('/dev/hidg0').exists(), 'mouse': Path('/dev/hidg1').exists()}))
