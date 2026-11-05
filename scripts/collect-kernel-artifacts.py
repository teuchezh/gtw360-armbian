#!/usr/bin/env python3
"""Validate GTW360 kernel packages and collect distributable build artifacts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--debs-dir', required=True, type=Path)
parser.add_argument('--output-dir', required=True, type=Path)
args = parser.parse_args()
required = {'linux-image-current-imx6', 'linux-dtb-current-imx6'}
allowed = required | {'linux-headers-current-imx6', 'linux-libc-dev-current-imx6'}
packages = {}
for deb in sorted(args.debs_dir.glob('*.deb')):
    fields = subprocess.check_output([
        'dpkg-deb', '-f', str(deb), 'Package', 'Version', 'Architecture',
    ], text=True)
    metadata = dict(line.split(': ', 1) for line in fields.splitlines())
    name = metadata['Package']
    if name not in allowed:
        continue
    if name in packages:
        raise SystemExit(f'Duplicate package: {name}')
    if metadata['Architecture'] != 'armhf':
        raise SystemExit(f'Wrong architecture: {deb.name}')
    packages[name] = (deb, metadata)
if required - packages.keys():
    raise SystemExit(f'Missing packages: {sorted(required - packages.keys())}')


def read_boot_files(package, wanted):
    result = {}
    process = subprocess.Popen(['dpkg-deb', '--fsys-tarfile', str(package)], stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=process.stdout, mode='r|') as archive:
            for member in archive:
                name = member.name.removeprefix('./')
                if member.isfile() and wanted(name):
                    result[name] = archive.extractfile(member).read()
    finally:
        process.stdout.close()
        status = process.wait()
    if status:
        raise SystemExit(f'Cannot read package: {package.name}')
    return result


boot = read_boot_files(packages['linux-image-current-imx6'][0],
                       lambda n: n.startswith(('boot/config-', 'boot/vmlinuz-')))
configs = [data.decode() for name, data in boot.items() if name.startswith('boot/config-')]
kernels = [(name, data) for name, data in boot.items() if name.startswith('boot/vmlinuz-')]
if len(configs) != 1 or len(kernels) != 1:
    raise SystemExit('Expected one kernel and configuration')
for option in ('TMPFS', 'SHMEM', 'EXT4_FS', 'VFAT_FS', 'DEVTMPFS', 'PROC_FS',
               'SYSFS', 'CGROUPS', 'FHANDLE', 'FEC', 'USB_CHIPIDEA_HOST', 'USB_CHIPIDEA_UDC'):
    if f'CONFIG_{option}=y' not in configs[0].splitlines():
        raise SystemExit(f'Missing required kernel option: CONFIG_{option}=y')
name, kernel = kernels[0]
kernel_version = name.removeprefix('boot/vmlinuz-')
if not kernel_version.startswith('6.18.60-'):
    raise SystemExit(f'Unexpected kernel version: {kernel_version}')
if struct.unpack_from('<I', kernel, 0x24)[0] != 0x016F2818:
    raise SystemExit('Kernel is not an ARM zImage')
dtbs = read_boot_files(packages['linux-dtb-current-imx6'][0],
                       lambda n: n.endswith('/imx6ull-gtw360.dtb'))
if len(dtbs) != 1:
    raise SystemExit('Missing or duplicate GTW360 DTB')
dtb = next(iter(dtbs.values()))
if not dtb.startswith(bytes.fromhex('d00dfeed')) or b'geniatech,imx6ull-gtw360\0' not in dtb:
    raise SystemExit('Wrong GTW360 device tree')

args.output_dir.mkdir(parents=True, exist_ok=True)
checksums = []
for deb, metadata in packages.values():
    target = args.output_dir / deb.name
    shutil.copyfile(deb, target)
    with target.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    checksums.append(f'{digest}  {deb.name}\n')
info = {
    'board': 'gtw360', 'kernel': kernel_version,
    'armbian_commit': '18e87d5385f9191419e6afa646080b68fbe7a1d5',
    'linux_commit': 'f45ed76d6791cf72ff1265ee93511175bbbc2f18',
    'project_commit': os.environ.get('GITHUB_SHA'),
    'packages': {name: metadata for name, (_, metadata) in packages.items()},
    'validation': 'ARM zImage, GTW360 DTB and required kernel options passed',
}
manifest = args.output_dir / 'BUILD-INFO.json'
manifest.write_text(json.dumps(info, indent=2) + '\n')
checksums.append(f'{hashlib.sha256(manifest.read_bytes()).hexdigest()}  {manifest.name}\n')
(args.output_dir / 'SHA256SUMS').write_text(''.join(checksums))
print(f'Validated {len(packages)} packages for {kernel_version}')
