#!/usr/bin/env python3
"""Verify the final GTW360 Armbian disk images without loop devices."""
import argparse
import shutil
import hashlib
import json
import lzma
from pathlib import Path
import struct
import subprocess
import uuid

project = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, default=project / 'artifacts')
out = parser.parse_args().output_dir.resolve()
manifest_path = out / 'gtw360-armbian-manifest.json'
m = json.loads(manifest_path.read_text())
prefix = (project / 'backups/emmc-first-4MiB.bin').read_bytes()
checksums = {}

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

previous_fit = None
for kind, info in m['images'].items():
    path = out / info['file']
    assert path.stat().st_size == info['size']
    with path.open('rb') as f:
        header = f.read(4 * 1024 * 1024)
        assert header[510:512] == b'\x55\xaa'
        if kind == 'emmc':
            assert header[512:] == prefix[512:]
        partitions = [struct.unpack_from('<II', header, 446 + 16*i + 8) for i in range(2)]
        expected = [(info['boot_offset']//512, info['boot_size']//512),
                    (info['root_offset']//512, info['root_size']//512)]
        if kind == 'usb':
            expected.reverse()
        assert partitions == expected
        f.seek(info['root_offset'] + 1024)
        superblock = f.read(1024)
        assert superblock[56:58] == b'\x53\xef'
        assert str(uuid.UUID(bytes=superblock[104:120])) == m['root_uuid']
        f.seek(info['boot_offset'] + 67)
        serial = f'{struct.unpack("<I", f.read(4))[0]:08X}'
        assert serial[:4] + '-' + serial[4:] == m['boot_uuid']
    all_hash = hashlib.sha256()
    parts = {name: hashlib.sha256() for name in ('root', 'boot')}
    position = 0
    with path.open('rb') as f:
        while chunk := f.read(8 * 1024 * 1024):
            all_hash.update(chunk)
            for name, digest in parts.items():
                start, size = info[name + '_offset'], info[name + '_size']
                lo, hi = max(position, start), min(position + len(chunk), start + size)
                if lo < hi:
                    digest.update(chunk[lo-position:hi-position])
            position += len(chunk)
    for name, digest in parts.items():
        assert digest.hexdigest() == info[name + '_sha256']
    checksums[path.name] = all_hash.hexdigest()
    name = 'fitImageA' if kind == 'emmc' else 'fitImage-rescue-gtw360'
    spec = str(path) + '@@' + str(info['boot_offset'])
    config = subprocess.check_output([
        str(Path(shutil.which('mtype'))), '-i', spec,
        '::config-' + m['kernel'],
    ]).decode().splitlines()
    for option in ('SHMEM', 'TMPFS', 'PROC_FS', 'SYSFS', 'DEVTMPFS',
                   'EXT4_FS', 'VFAT_FS', 'UNIX', 'CGROUPS', 'FHANDLE'):
        assert 'CONFIG_' + option + '=y' in config, option + ' required for Armbian boot'
    fit = subprocess.check_output([str(Path(shutil.which('mtype'))), '-i', spec, '::' + name])
    if kind == 'emmc':
        assert fit == subprocess.check_output([str(Path(shutil.which('mtype'))), '-i', spec, '::fitImageB'])
    props = fdt(fit)
    for component in ('kernel', 'fdt', 'ramdisk'):
        data = props[(f'/images/{component}', 'data')]
        assert hashlib.sha256(data).digest() == props[(f'/images/{component}/hash', 'value')]
    dt = fdt(props[('/images/fdt', 'data')])
    assert f'root=UUID={m["root_uuid"]}'.encode() in dt[('/chosen', 'bootargs')].split()
    assert b'geniatech,imx6ull-gtw360' in dt[('/', 'compatible')]
    assert struct.unpack_from('<I', props[('/images/kernel', 'data')], 0x24)[0] == 0x016f2818
    if previous_fit is not None:
        assert fit == previous_fit
    previous_fit = fit
    compressed = Path(str(path) + '.xz')
    expanded = hashlib.sha256()
    expanded_size = 0
    with lzma.open(compressed, 'rb') as f:
        while chunk := f.read(8 * 1024 * 1024):
            expanded.update(chunk)
            expanded_size += len(chunk)
    assert expanded_size == info['size'] and expanded.hexdigest() == checksums[path.name]
    with compressed.open('rb') as f:
        checksums[compressed.name] = hashlib.file_digest(f, 'sha256').hexdigest()
    print(f'{kind}: MBR, filesystem UUIDs, partition hashes, FIT and xz passed', flush=True)
checksums[manifest_path.name] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
(out / 'ARMBIAN-SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name,digest in checksums.items()))
