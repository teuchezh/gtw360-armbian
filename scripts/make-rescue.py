#!/usr/bin/env python3
"""Build RAM diagnostics and a USB boot image from GTW360 kernel packages."""
import argparse
import gzip
import lzma
import shutil
import subprocess
import tempfile
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--rescue-rootfs', required=True, type=Path)
p.add_argument('--image-deb', required=True, type=Path)
p.add_argument('--dtb-deb', required=True, type=Path)
a = p.parse_args()
project = Path(__file__).resolve().parent.parent
root = a.rescue_rootfs.resolve()
out = project / 'artifacts'
out.mkdir(exist_ok=True)

def run(*args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)

with tempfile.TemporaryDirectory(prefix='gtw360-rescue-', dir=out) as tmp:
    stage = Path(tmp)
    run('dpkg-deb', '-x', a.image_deb.resolve(), stage)
    run('dpkg-deb', '-x', a.dtb_deb.resolve(), stage)
    module_roots = list((stage / 'lib/modules').glob('*'))
    if len(module_roots) != 1:
        raise SystemExit(f'Expected one kernel version: {module_roots}')
    version = module_roots[0].name
    run('depmod', '-b', stage, version)
    selected = set()
    for module in ('libcomposite', 'usb_f_hid', 'usb_f_mass_storage', 'uvcvideo', 'usb_storage', 'imx2_wdt', 'nvmem_imx_ocotp', 'imx6q_cpufreq', 'nls_cp437', 'nls_iso8859_1'):
        result = run('modprobe', '-d', stage, '-S', version, '--show-depends', module,
                     stdout=subprocess.PIPE, text=True)
        for line in result.stdout.splitlines():
            if line.startswith('insmod '):
                selected.add(Path(line.split()[1]))
    dest = root / 'lib/modules' / version
    dest.mkdir(parents=True, exist_ok=True)
    for src in sorted(selected):
        name = src.name
        data = src.read_bytes()
        if name.endswith('.zst'):
            data = run('zstd', '-dc', src, stdout=subprocess.PIPE).stdout
            name = name[:-4]
        elif name.endswith('.xz'):
            data, name = lzma.decompress(data), name[:-3]
        elif name.endswith('.gz'):
            data, name = gzip.decompress(data), name[:-3]
        (dest / name).write_bytes(data)
    for name in ('modules.builtin', 'modules.builtin.modinfo', 'modules.order'):
        src = module_roots[0] / name
        if src.exists():
            shutil.copyfile(src, dest / name)
    run('depmod', '-b', root, version)
    files = ['.'] + sorted(str(x.relative_to(root)) for x in root.rglob('*'))
    archive = run('cpio', '--null', '-o', '-H', 'newc', '--owner=0:0', cwd=root,
                  input=('\0'.join(files) + '\0').encode(), stdout=subprocess.PIPE).stdout
    initrd = out / 'gtw360-rescue.cpio.gz'
    initrd.write_bytes(gzip.compress(archive, mtime=0))
    kernels = list((stage / 'boot').glob('vmlinuz-*'))
    dtbs = list((stage / 'boot').rglob('imx6ull-gtw360.dtb'))
    if len(kernels) != 1 or len(dtbs) != 1:
        raise SystemExit(f'Boot files ambiguous: {kernels}, {dtbs}')
    for role in ('host', 'usb0-peripheral', 'usb1-peripheral'):
        cmd = ['python3', project / 'scripts/make-fit.py', '--kernel', kernels[0],
               '--dtb', dtbs[0], '--initrd', initrd, '--root', '/dev/ram0',
               '--output', out / f'gtw360-rescue-{role}.fit']
        if role != 'host':
            cmd += ['--peripheral', role[3]]
        run(*cmd)
    mib = 1024 * 1024
    disk = out / 'gtw360-rescue-usb.img'
    with disk.open('wb') as f:
        f.truncate(96 * mib)
    run('sfdisk', '--no-reread', '--no-tell-kernel', disk, input=
        'label: dos\nunit: sectors\n\nstart=2048,size=32768,type=e\nstart=34816,size=131072,type=e\n', text=True)
    for number, size, offset, label in ((1, 16, 1, 'GTWINFO'), (2, 64, 17, 'GTWRESCUE')):
        part = stage / f'fat{number}.img'
        with part.open('wb') as f:
            f.truncate(size * mib)
        run('mkfs.vfat', '-F', '16', '-n', label, part)
        if number == 1:
            run(Path(shutil.which('mcopy')), '-i', part,
                project / 'rescue/README.md', '::README.TXT')
        else:
            run(Path(shutil.which('mcopy')), '-i', part,
                out / 'gtw360-rescue-host.fit', '::fitImage-rescue-gtw360')
        with disk.open('r+b') as dst, part.open('rb') as src:
            dst.seek(offset * mib)
            shutil.copyfileobj(src, dst)
    with disk.open('rb') as src, lzma.open(str(disk) + '.xz', 'wb', preset=3) as dst:
        shutil.copyfileobj(src, dst)
    print(f'Kernel {version}; {len(selected)} module dependencies; {disk}.xz')
