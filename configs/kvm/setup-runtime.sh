#!/bin/sh
set -eu
cd /opt/gtw360/kvmd-4.100
python3 -m venv --system-site-packages /opt/gtw360/venv
/opt/gtw360/venv/bin/pip install --no-deps --no-build-isolation .
mkdir -p /usr/share/kvmd /etc/kvmd/nginx /etc/kvmd/override.d /run/kvmd
cp -r web extras /usr/share/kvmd/
cp -r contrib/keymaps /usr/share/kvmd/
cp configs/kvmd/*.yaml /etc/kvmd/
cp configs/kvmd/main/v2-hdmiusb-rpi4.yaml /etc/kvmd/main.yaml
cp configs/nginx/*.conf /etc/kvmd/nginx/
cp configs/kvmd/web.css /etc/kvmd/
cat > /etc/kvmd/override.yaml <<'YAML'
kvmd:
    hid:
        type: otg
        keyboard:
            device: /dev/hidg0
        mouse:
            device: /dev/hidg1
            absolute: false
            horizontal_wheel: false
        mouse_alt:
            device: ''
    atx:
        type: disabled
    msd:
        type: disabled
    streamer:
        resolution:
            default: 1280x720
        desired_fps: 15
        cmd:
            - /usr/bin/ustreamer
            - --device=/dev/video0
            - --persistent
            - --format=mjpeg
            - --resolution={resolution}
            - --desired-fps={desired_fps}
            - --unix={unix}
            - --unix-rm
            - --unix-mode=0666
YAML


printf 'PIKVM_MODEL=GTW360\nPIKVM_VIDEO=hdmiusb\nPIKVM_BOARD=gtw360\n' > /usr/share/kvmd/platform
python3 - <<'CONFIG'
from pathlib import Path
import yaml
p=Path('/etc/kvmd/override.yaml');s=yaml.safe_load(p.read_text())
s['kvmd']['info']={'hw':{'vcgencmd_cmd':['/bin/true']}}
s['otgnet']={'commands':{'iptables_cmd':['/bin/true']}}
s['janus']={'cmd':['/bin/true']}
p.write_text(yaml.safe_dump(s))
for name in ['ipmipasswd','vncpasswd','totp.secret']:
    Path('/etc/kvmd/'+name).touch(mode=0o600)
p=Path('/opt/gtw360/venv/lib/python3.13/site-packages/kvmd/apps/kvmd/info/health.py')
s=p.read_text().replace('        cmd = [*self.__vcgencmd_cmd, arg]', '        if self.__vcgencmd_cmd == ["/bin/true"]:\n            return None\n        cmd = [*self.__vcgencmd_cmd, arg]')
p.write_text(s)
CONFIG
