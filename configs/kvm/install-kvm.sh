#!/bin/bash
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run as root'; exit 1; }
[[ $(findmnt -n -o SOURCE /) == /dev/mmcblk1p2 ]] || { echo 'Boot from installed eMMC first'; exit 1; }
compgen -G '/sys/class/udc/*' >/dev/null || { echo 'Run /root/usb-gadget.sh enable, then reboot first'; exit 1; }
[[ ! -e /opt/gtw360/kvmd-4.100 ]] || { echo 'KVMD installation already exists; inspect it before reinstalling'; exit 1; }
[[ ! -e /root/gtw360-kvm-login ]] || { echo 'Existing KVM credentials found'; exit 1; }
mkdir -p /opt/gtw360
cp -a /etc/nginx /opt/gtw360/nginx-before-kvm 2>/dev/null || true
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends git gcc libc6-dev python3-dev python3-venv python3-setuptools python3-yaml python3-aiohttp python3-aiofiles python3-async-lru python3-passlib python3-bcrypt python3-pyotp python3-qrcode python3-serial python3-serial-asyncio python3-setproctitle python3-psutil python3-netifaces python3-systemd python3-dbus python3-dbus-next python3-pygments python3-pil python3-hid python3-zstandard python3-mako python3-usb python3-pyudev python3-evdev python3-xlib python3-libgpiod libxkbcommon0 nginx openssl apache2-utils ustreamer
fetch() {
    git init "$2"
    git -C "$2" remote add origin "$1"
    git -C "$2" fetch --depth=1 origin "$3"
    git -C "$2" checkout --detach FETCH_HEAD
}
fetch https://github.com/pikvm/kvmd /opt/gtw360/kvmd-4.100 refs/tags/v4.100
fetch https://github.com/pikvm/ustreamer /opt/gtw360/ustreamer 11fd828ab00c01a39bd0843ef442ef0b6d3cac41
sh /usr/local/lib/gtw360/kvm/setup-runtime.sh
cd /opt/gtw360/ustreamer/python
/opt/gtw360/venv/bin/pip install --no-deps --no-build-isolation .
/opt/gtw360/venv/bin/kvmd --help >/dev/null
python3 /usr/local/lib/gtw360/kvm/configure-web.py
# Match KVMD relative mouse reports, including vertical wheel.
/opt/gtw360/venv/bin/python3 - <<'PY'
from pathlib import Path
from kvmd.apps.otg.hid.mouse import make_mouse_hid
import subprocess
h=make_mouse_hid(False,False)
subprocess.run(['systemctl','stop','gtw360-hid-test'],check=True)
g=Path('/sys/kernel/config/usb_gadget/gtw360-hid-test')
for p in (g/'configs/c.1').glob('hid.*'):
    p.unlink()
p=Path('/usr/local/sbin/gtw360-hid-test');s=p.read_text()
a=s.index("    mouse = bytes.fromhex('");b=s.index('\n',a)
s=s[:a]+"    mouse = bytes.fromhex('"+h.report_descriptor.hex()+"')"+s[b:]
s=s.replace("('hid.mouse', 2, 3, mouse)","('hid.mouse', 2, 4, mouse)")
p.write_text(s)
PY
systemctl daemon-reload
systemctl enable --now gtw360-hid-test kvmd
nginx -t
systemctl enable nginx
systemctl restart nginx
echo 'KVM installed. Open https://DEVICE-IP/ . Credentials: /root/gtw360-kvm-login'
echo 'Self-signed certificate. ATX and mass storage are disabled.'
