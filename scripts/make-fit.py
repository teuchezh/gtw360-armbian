#!/usr/bin/env python3
"""Package a GTW360 FIT without writing to a device."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--kernel', required=True, type=Path)
p.add_argument('--dtb', required=True, type=Path)
p.add_argument('--initrd', type=Path)
p.add_argument('--root', default='/dev/mmcblk1p2')
p.add_argument('--peripheral', choices=['0', '1'], help='Enable only after mapping the physical USB port')
p.add_argument('--output', required=True, type=Path)
a = p.parse_args()
for value in (a.kernel, a.dtb, a.initrd):
    if value is not None and not value.is_file():
        p.error(f'File missing: {value}')
if any(c.isspace() for c in a.root):
    p.error('--root must be one kernel argument value')
a.output = a.output.resolve()
a.output.parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='gtw360-fit-') as tmp:
    d = Path(tmp)
    shutil.copyfile(a.kernel, d / 'zImage')
    shutil.copyfile(a.dtb, d / 'board.dtb')
    def put(node, prop, value):
        subprocess.run(['fdtput', '-t', 's', str(d / 'board.dtb'), node, prop, value], check=True)
    put('/chosen', 'bootargs', f'console=ttymxc0,115200 root={a.root} rootwait rw net.ifnames=0')
    if a.peripheral is not None:
        address = ['2184000', '2184200'][int(a.peripheral)]
        put(f'/soc/bus@2100000/usb@{address}', 'dr_mode', 'peripheral')
    ramdisk = ''
    ref = ''
    if a.initrd:
        shutil.copyfile(a.initrd, d / 'initrd')
        ramdisk = '''ramdisk { description = "Armbian initramfs";
            data = /incbin/("initrd"); type = "ramdisk"; arch = "arm";
            os = "linux"; compression = "none"; load = <0x84800000>;
            hash { algo = "sha256"; }; };'''
        ref = 'ramdisk = "ramdisk";'
    its = '''/dts-v1/;
/ { description = "GTW360 experimental Armbian"; #address-cells = <1>;
 images {
  kernel { description = "Linux"; data = /incbin/("zImage");
   type = "kernel"; arch = "arm"; os = "linux"; compression = "none";
   load = <0x80800000>; entry = <0x80800000>; hash { algo = "sha256"; }; };
  fdt { description = "Geniatech GTW360"; data = /incbin/("board.dtb");
   type = "flat_dt"; arch = "arm"; compression = "none";
   hash { algo = "sha256"; }; };
  RAMDISK
 };
 configurations { default = "standard";
  standard { description = "GTW360"; kernel = "kernel"; fdt = "fdt"; RAMDISK_REF };
 };
};
'''.replace('RAMDISK_REF', ref).replace('RAMDISK', ramdisk)
    (d / 'image.its').write_text(its)
    subprocess.run(['mkimage', '-f', 'image.its', 'fitImage'], cwd=d, check=True)
    # The vendor loader places FIT at 0x88800000; reject oversized images.
    if (d / 'fitImage').stat().st_size > 64 * 1024 * 1024:
        raise SystemExit('FIT exceeds the conservative 64 MiB limit')
    shutil.copyfile(d / 'fitImage', a.output)
print(a.output)
