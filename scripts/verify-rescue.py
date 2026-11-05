#!/usr/bin/env python3
"""Check FIT payloads, RAM initramfs and the diagnostic USB image."""
import gzip
import shutil
import hashlib
import lzma
import struct
import subprocess
from pathlib import Path

project = Path(__file__).resolve().parent.parent

def fdt(blob):
    magic, size, offset, strings = struct.unpack_from('>4I', blob)
    assert magic == 0xd00dfeed and size <= len(blob)
    props, stack, i = {}, [], offset
    while True:
        tag = struct.unpack_from('>I', blob, i)[0]
        i += 4
        if tag == 1:
            end = blob.index(b'\0', i)
            stack.append(blob[i:end].decode())
            i = (end + 4) & ~3
        elif tag == 2:
            stack.pop()
        elif tag == 3:
            length, name = struct.unpack_from('>2I', blob, i)
            i += 8
            start = strings + name
            end = blob.index(b'\0', start)
            props[('/' + '/'.join(filter(None, stack)), blob[start:end].decode())] = blob[i:i+length]
            i = (i + length + 3) & ~3
        elif tag == 4:
            pass
        elif tag == 9:
            return props
        else:
            raise AssertionError(tag)

def cpio(blob):
    result, i = {}, 0
    while True:
        header = blob[i:i+110]
        assert header[:6] == b'070701'
        size, namesize = int(header[54:62], 16), int(header[94:102], 16)
        name = blob[i+110:i+110+namesize-1].decode()
        start = (i + 110 + namesize + 3) & ~3
        if name == 'TRAILER!!!':
            return result
        result[name] = (int(header[14:22], 16), blob[start:start+size])
        i = (start + size + 3) & ~3

for role, expected in [('host', ('host', 'host')), ('usb0-peripheral', ('peripheral', 'host')), ('usb1-peripheral', ('host', 'peripheral'))]:
    props = fdt((project / f'artifacts/gtw360-rescue-{role}.fit').read_bytes())
    for name in ('kernel', 'fdt', 'ramdisk'):
        payload = props[(f'/images/{name}', 'data')]
        assert hashlib.sha256(payload).digest() == props[(f'/images/{name}/hash', 'value')]
    dt = fdt(props[('/images/fdt', 'data')])
    assert b'root=/dev/ram0' in dt[('/chosen', 'bootargs')]
    for address, value in zip(('2184000', '2184200'), expected):
        assert dt[(f'/soc/bus@2100000/usb@{address}', 'dr_mode')] == value.encode() + b'\0'
    assert struct.unpack_from('<I', props[('/images/kernel', 'data')], 0x24)[0] == 0x016f2818
    files = cpio(gzip.decompress(props[('/images/ramdisk', 'data')]))
    assert files['init'][0] & 0o111
    assert b'dropbear -R -s -E -p 22' in files['init'][1]
    for path in ('bin/busybox', 'usr/sbin/dropbear', 'etc/dropbear/authorized_keys', 'sbin/kmodloader', 'etc/shells', 'usr/sbin/rescue-watchdog'):
        assert path in files, path
    for module in ('libcomposite.ko', 'usb_f_hid.ko', 'usb_f_mass_storage.ko', 'uvcvideo.ko', 'imx2_wdt.ko'):
        assert any(n.endswith('/' + module) for n in files), module
    builtins = next(data for name, (_, data) in files.items() if name.endswith('/modules.builtin'))
    assert b'kernel/drivers/usb/storage/usb-storage.ko\n' in builtins
    print(f'{role}: hashes, ARM zImage, USB roles and initramfs passed')
image_path = project / 'artifacts/gtw360-rescue-usb.img'
image = image_path.read_bytes()
assert image[510:512] == b'\x55\xaa'
assert struct.unpack_from('<II', image, 462+8) == (34816, 131072)
fit = subprocess.check_output([str(Path(shutil.which('mtype'))), '-i', str(image_path)+'@@17825792', '::fitImage-rescue-gtw360'])
assert fit == (project / 'artifacts/gtw360-rescue-host.fit').read_bytes()
assert lzma.decompress(Path(str(image_path)+'.xz').read_bytes()) == image
print('USB partition 2 boot file and xz round-trip passed')
