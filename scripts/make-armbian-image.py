#!/usr/bin/env python3
"""Package a GTW360 Armbian rootfs into regular image files without loop devices."""
import argparse
from contextlib import nullcontext
import hashlib
import json
import lzma
import math
import ipaddress
import re
import os
from pathlib import Path
import secrets
import shutil
import struct
import subprocess
import tempfile
import time
import uuid

project = Path(__file__).resolve().parent.parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--rootfs-archive', required=True, type=Path)
p.add_argument('--vendor-prefix', type=Path)
p.add_argument('--usb-only', action='store_true')
p.add_argument('--generic', action='store_true', help='DHCP and Armbian first-login setup')
p.add_argument('--authorized-key', type=Path)
p.add_argument('--output-dir', required=True, type=Path)
p.add_argument('--ip-address')
p.add_argument('--gateway')
p.add_argument('--dns')
p.add_argument('--mac-address')
p.add_argument('--kernel-deb', action='append', default=[], type=Path,
               help='Install a rebuilt kernel package into the exported rootfs')
p.add_argument('--root-uuid', help='Preserve an existing root filesystem UUID')
p.add_argument('--boot-serial', help='Preserve an existing eight-digit FAT serial')
a = p.parse_args()
if not a.generic and not all([a.ip_address, a.gateway, a.dns, a.mac_address, a.authorized_key]):
    p.error('Personalized mode requires network parameters and authorized key')
address = str(ipaddress.IPv4Interface(a.ip_address)) if not a.generic else 'dhcp'
gateway = str(ipaddress.IPv4Address(a.gateway)) if not a.generic else None
dns = str(ipaddress.IPv4Address(a.dns)) if not a.generic else None
mac = a.mac_address.lower() if not a.generic else None
if mac:
    assert re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', mac), 'Invalid MAC'
output = a.output_dir.resolve()
output.mkdir(parents=True, exist_ok=True)
mib = 1024 * 1024
mcopy = shutil.which('mcopy')
if not mcopy:
    raise SystemExit('Install mtools first')
mtools = Path(mcopy).parent

def run(*args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)

def write(root, name, text, mode=0o644):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(mode)

def sparse_copy(src, dst, offset):
    digest = hashlib.sha256()
    zero = bytes(4 * mib)
    with src.open('rb') as inp, dst.open('r+b') as out:
        out.seek(offset)
        while chunk := inp.read(len(zero)):
            digest.update(chunk)
            if chunk == zero[:len(chunk)]:
                out.seek(len(chunk), 1)
            else:
                out.write(chunk)
    return digest.hexdigest()

def region_hash(path, offset, size):
    digest = hashlib.sha256()
    with path.open('rb') as f:
        f.seek(offset)
        while size:
            chunk = f.read(min(size, 4 * mib))
            if not chunk:
                raise RuntimeError('Image truncated')
            digest.update(chunk)
            size -= len(chunk)
    return digest.hexdigest()

if not a.usb_only and not a.vendor_prefix:
    p.error('--vendor-prefix required unless --usb-only')
prefix = a.vendor_prefix.read_bytes() if a.vendor_prefix else b''
if prefix:
    assert len(prefix) == 4 * mib and prefix[510:512] == b'\x55\xaa'
key = a.authorized_key.read_text().strip() + '\n' if not a.generic else ''
if key:
    assert key.startswith('ssh-ed25519 ')
root_uuid = str(uuid.UUID(a.root_uuid)) if a.root_uuid else str(uuid.uuid4())
boot_serial = a.boot_serial.upper() if a.boot_serial else secrets.token_hex(4).upper()
assert len(boot_serial) == 8 and all(c in '0123456789ABCDEF' for c in boot_serial)
boot_uuid = boot_serial[:4] + '-' + boot_serial[4:]
password_file = project / 'backups/armbian-root-password.txt'
password_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
if not password_file.exists():
    with os.fdopen(os.open(password_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as f:
        f.write(secrets.token_urlsafe(24) + '\n')
password_hash = run('openssl', 'passwd', '-6', '-stdin', input='1234\n' if a.generic else password_file.read_text(),
                    text=True, stdout=subprocess.PIPE).stdout.strip()
manifest = {'root_uuid': root_uuid, 'boot_uuid': boot_uuid, 'ip': address,
            'gateway': gateway, 'vendor_prefix_sha256': hashlib.sha256(prefix).hexdigest(),
            'hardware_boot_tested': False, 'images': {}}

with nullcontext(tempfile.mkdtemp(prefix='gtw360-armbian-', dir=output)) as tmp:
    work = Path(tmp)
    root = work / 'rootfs'
    root.mkdir()
    run('tar', '--zstd', '--numeric-owner', '--xattrs', '--acls', '-xpf',
        a.rootfs_archive.resolve(), '-C', root)
    versions = list((root / 'lib/modules').iterdir())
    assert len(versions) == 1, versions
    kernel_version = versions[0].name
    manifest['kernel'] = kernel_version
    manifest['armbian_release'] = (root / 'etc/armbian-release').read_text()
    write(root, 'etc/fstab',
          f'UUID={root_uuid} / ext4 defaults,noatime,errors=remount-ro 0 1\n'
          f'UUID={boot_uuid} /boot vfat defaults 0 2\n')
    default_network = root / 'etc/netplan/10-dhcp-all-interfaces.yaml'
    default_network.unlink(missing_ok=True)
    if a.generic:
        write(root, 'etc/netplan/10-gtw360.yaml', 'network:\n  version: 2\n  renderer: networkd\n  ethernets:\n    eth0:\n      dhcp4: true\n', 0o600)
    else:
        write(root, 'etc/netplan/10-gtw360.yaml', f'''network:
      version: 2
      renderer: networkd
      ethernets:
        eth0:
          match:
            name: eth0
          macaddress: "{mac}"
          dhcp4: false
          dhcp6: false
          addresses: [{address}]
          routes:
            - to: default
              via: {gateway}
          nameservers:
            addresses: [{dns}]
    ''', 0o600)
    write(root, 'etc/hostname', 'gtw360\n')
    if key:
        write(root, 'root/.ssh/authorized_keys', key, 0o600)
        (root / 'root/.ssh').chmod(0o700)
    else:
        (root / 'root/.ssh/authorized_keys').unlink(missing_ok=True)
    write(root, 'etc/ssh/sshd_config.d/00-gtw360.conf',
          ('PermitRootLogin yes\nPasswordAuthentication yes\n' if a.generic else
           'PermitRootLogin prohibit-password\nPasswordAuthentication no\n') +
          'KbdInteractiveAuthentication no\nPubkeyAuthentication yes\n')
    shadow = root / 'etc/shadow'
    entries = shadow.read_text().splitlines()
    for i, line in enumerate(entries):
        if line.startswith('root:'):
            fields = line.split(':')
            fields[1:3] = [password_hash, '0' if a.generic else str(int(time.time() // 86400))]
            entries[i] = ':'.join(fields)
            break
    else:
        raise RuntimeError('Root account missing')
    shadow.write_text('\n'.join(entries) + '\n')
    shadow.chmod(0o640)
    if a.generic:
        (root / 'root/.not_logged_in_yet').touch()
    else:
        (root / 'root/.not_logged_in_yet').unlink(missing_ok=True)
    for unit in ('getty@.service', 'serial-getty@.service'):
        path = root / f'etc/systemd/system/{unit}.d/override.conf'
        if path.exists() and '--autologin root' in path.read_text():
            path.unlink()
    for path in (root / 'etc/ssh').glob('ssh_host_*_key*'):
        path.unlink()
    write(root, 'etc/systemd/system/gtw360-ssh-hostkeys.service', '''[Unit]
Description=Generate GTW360 SSH host keys
Before=ssh.service
ConditionPathExists=!/etc/ssh/ssh_host_ed25519_key

[Service]
Type=oneshot
ExecStart=/usr/bin/ssh-keygen -A
RemainAfterExit=yes
''')
    write(root, 'etc/systemd/system/ssh.service.d/10-gtw360-hostkeys.conf',
          '[Unit]\nRequires=gtw360-ssh-hostkeys.service\nAfter=gtw360-ssh-hostkeys.service\n')
    run('systemctl', '--root', root, 'enable', 'ssh.service')
    for name, target, mode in (
        ('gtw360-zigbee-init', 'usr/local/sbin/gtw360-zigbee-init', 0o755),
        ('gtw360-zigbee.service', 'etc/systemd/system/gtw360-zigbee.service', 0o644),
        ('70-gtw360-zigbee.rules', 'etc/udev/rules.d/70-gtw360-zigbee.rules', 0o644),
    ):
        write(root, target, (project / 'configs/zigbee' / name).read_text(), mode)
    run('systemctl', '--root', root, 'enable', 'gtw360-zigbee.service')
    write(root, 'usr/local/sbin/gtw360-leds-init',
          (project / 'configs/leds/gtw360-leds-init').read_text(), 0o755)
    write(root, 'etc/systemd/system/gtw360-leds.service',
          (project / 'configs/leds/gtw360-leds.service').read_text())
    run('systemctl', '--root', root, 'enable', 'gtw360-leds.service')
    mounts = []
    try:
        for target, args in [('dev', ['--bind', '/dev']), ('proc', ['-t', 'proc', 'proc']),
                             ('sys', ['-t', 'sysfs', 'sysfs'])]:
            path = root / target
            assert path.is_dir() and not path.is_symlink()
            run('mount', *args, path)
            mounts.append(path)
        if a.kernel_deb:
            packages = root / 'tmp/gtw360-kernel-packages'
            packages.mkdir()
            for deb in a.kernel_deb:
                shutil.copyfile(deb, packages / deb.name)
            run('chroot', root, '/usr/bin/dpkg', '-i',
                *['/tmp/gtw360-kernel-packages/' + deb.name for deb in a.kernel_deb])
            shutil.rmtree(packages)
            versions = list((root / 'lib/modules').iterdir())
            assert len(versions) == 1, versions
            kernel_version = versions[0].name
            manifest['kernel'] = kernel_version
        run('chroot', root, '/usr/sbin/netplan', 'generate')
        test_key = root / 'tmp/gtw360-sshd-validation-key'
        run('ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', test_key)
        (root / 'run/sshd').mkdir(parents=True, exist_ok=True)
        ssh_config = run('chroot', root, '/usr/sbin/sshd', '-T', '-h',
                         '/tmp/gtw360-sshd-validation-key', '-C',
                         'user=root,host=gtw360,addr=203.0.113.1',
                         stdout=subprocess.PIPE, text=True).stdout
        values = dict(line.split(' ', 1) for line in ssh_config.splitlines())
        assert values['passwordauthentication'] == ('yes' if a.generic else 'no')
        assert values['pubkeyauthentication'] == 'yes'
        assert values['permitrootlogin'] in (('yes',) if a.generic else ('without-password', 'prohibit-password'))
        test_key.unlink()
        Path(str(test_key) + '.pub').unlink()
        run('chroot', root, '/usr/bin/apt-mark', 'hold',
            'linux-image-current-imx6', 'linux-dtb-current-imx6')
        run('chroot', root, '/usr/sbin/mkinitramfs', '-o',
            f'/boot/initrd.img-{kernel_version}', kernel_version,
            env={**os.environ, 'DEBIAN_FRONTEND': 'noninteractive'})
    finally:
        unmount_errors = []
        for path in reversed(mounts):
            try:
                run('umount', path)
            except subprocess.CalledProcessError:
                unmount_errors.append(str(path))
        if unmount_errors:
            raise RuntimeError(f'Chroot mounts remain; staging retained: {unmount_errors}')
    boot = root / 'boot'
    kernel = boot / f'vmlinuz-{kernel_version}'
    dtbs = list(boot.rglob('imx6ull-gtw360.dtb'))
    assert len(dtbs) == 1, dtbs
    run('python3', project / 'scripts/make-fit.py', '--kernel', kernel,
        '--dtb', dtbs[0], '--initrd', boot / f'initrd.img-{kernel_version}',
        '--root', f'UUID={root_uuid}', '--output', boot / 'fitImageA')
    shutil.copyfile(boot / 'fitImageA', boot / 'fitImageB')
    write(root, 'boot/armbianEnv.txt', f'rootdev=UUID={root_uuid}\nfdtfile=nxp/imx/imx6ull-gtw360.dtb\n')
    flat_boot = work / 'boot-content'
    flat_boot.mkdir()
    def copy_boot(source, dest, ancestors=()):
        hops = 0
        while source.is_symlink():
            hops += 1
            assert hops < 20
            link = os.readlink(source)
            source = root / link.lstrip('/') if link.startswith('/') else source.parent / link
            source = Path(os.path.normpath(source))
        assert source.is_relative_to(boot), source
        if not source.exists():
            return
        if source.is_dir():
            assert source not in ancestors, source
            dest.mkdir(exist_ok=True)
            for child in source.iterdir():
                copy_boot(child, dest / child.name, ancestors + (source,))
        elif source.is_file():
            shutil.copyfile(source, dest)
    for child in boot.iterdir():
        copy_boot(child, flat_boot / child.name)
    boot.rename(work / 'original-boot')
    boot.mkdir()
    used = int(run('du', '--apparent-size', '-s', '--block-size=1', root,
                   stdout=subprocess.PIPE, text=True).stdout.split()[0])
    root_mib = max(2048, math.ceil((used * 1.25 / mib + 256) / 64) * 64)
    assert root_mib + 260 <= 7456, root_mib
    root_image = work / 'root.ext4'
    with root_image.open('wb') as f:
        f.truncate(root_mib * mib)
    run('mkfs.ext4', '-F', '-q', '-m', '1', '-L', 'armbi_root', '-U', root_uuid,
        '-O', '^orphan_file', '-d', root, root_image)
    run('e2fsck', '-f', '-n', root_image)
    root_hash = region_hash(root_image, 0, root_image.stat().st_size)
    for kind in (('usb',) if a.usb_only else ('emmc', 'usb')):
        fat = work / f'boot-{kind}.fat'
        with fat.open('wb') as f:
            f.truncate(256 * mib)
        run('mkfs.vfat', '-F', '32', '-n', 'GTW_BOOT', '-i', boot_serial, fat)
        items = [x for x in flat_boot.iterdir() if x.name not in ('fitImageA', 'fitImageB')]
        run(mtools / 'mcopy', '-s', '-i', fat, *items, '::')
        for name in (('fitImageA', 'fitImageB') if kind == 'emmc' else ('fitImage-rescue-gtw360',)):
            run(mtools / 'mcopy', '-i', fat, flat_boot / 'fitImageA', '::' + name)
        image = output / f'gtw360-armbian-trixie-{kind}.img'
        with image.open('wb') as f:
            f.truncate((root_mib + 260) * mib)
        if kind == 'emmc':
            parts = [(4, 256, 'c'), (260, root_mib, '83')]
            root_offset, boot_offset = 260 * mib, 4 * mib
        else:
            parts = [(4, root_mib, '83'), (4 + root_mib, 256, 'c')]
            root_offset, boot_offset = 4 * mib, (4 + root_mib) * mib
        table = 'label: dos\nunit: sectors\n\n' + ''.join(
            f'start={start*2048},size={size*2048},type={type_}\n' for start,size,type_ in parts)
        run('sfdisk', '--no-reread', '--no-tell-kernel', image, input=table, text=True)
        if kind == 'emmc':
            with image.open('r+b') as f:
                f.seek(512)
                f.write(prefix[512:])
        assert sparse_copy(root_image, image, root_offset) == root_hash
        boot_hash = sparse_copy(fat, image, boot_offset)
        assert region_hash(image, root_offset, root_image.stat().st_size) == root_hash
        assert region_hash(image, boot_offset, fat.stat().st_size) == boot_hash
        boot_name = 'fitImageA' if kind == 'emmc' else 'fitImage-rescue-gtw360'
        embedded = run(mtools / 'mtype', '-i', str(image) + '@@' + str(boot_offset),
                       '::' + boot_name, stdout=subprocess.PIPE).stdout
        assert embedded == (flat_boot / 'fitImageA').read_bytes()
        with image.open('rb') as src, lzma.open(str(image)+'.xz', 'wb', preset=3) as dst:
            shutil.copyfileobj(src, dst)
        manifest['images'][kind] = {'file': image.name, 'size': image.stat().st_size,
            'root_offset': root_offset, 'root_size': root_image.stat().st_size,
            'boot_offset': boot_offset, 'boot_size': fat.stat().st_size,
            'root_sha256': root_hash, 'boot_sha256': boot_hash}
        print(f'Created and verified {image}.xz', flush=True)
(output / 'gtw360-armbian-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print('Armbian image assembly completed', flush=True)

# Delete staging only after confirming no mounts remain below it.
mountpoints = [line.split()[4] for line in Path('/proc/self/mountinfo').read_text().splitlines()]
if any(m == str(work) or m.startswith(str(work) + '/') for m in mountpoints):
    raise RuntimeError(f'Mounted staging retained: {work}')
shutil.rmtree(work)
