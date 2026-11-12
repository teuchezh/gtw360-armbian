#!/bin/bash
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run as root'; exit 1; }
[[ $(findmnt -n -o SOURCE /) == /dev/mmcblk1p2 ]] || { echo 'Install and boot from eMMC first'; exit 1; }
mode=${1:-}
[[ $mode == enable || $mode == disable ]] || { echo 'Usage: /root/usb-gadget.sh enable|disable'; exit 1; }
[[ $(findmnt -n -o SOURCE /boot) == /dev/mmcblk1p1 ]] || { echo 'Unexpected boot partition'; exit 1; }
mkdir -p /etc/gtw360
cfg=/etc/gtw360/fw_env.config
printf '/dev/mmcblk1 0x2fe000 0x2000 0x200\n/dev/mmcblk1 0x2fc000 0x2000 0x200\n' > "$cfg"
fw_printenv -c "$cfg" > /etc/gtw360/uboot-env-before-usb-change.txt
if [[ $mode == enable ]]; then
    mapfile -t kernels < <(find /boot -maxdepth 1 -type f -name 'vmlinuz-*')
    mapfile -t dtbs < <(find /boot -type f -name imx6ull-gtw360.dtb)
    [[ ${#kernels[@]} == 1 && ${#dtbs[@]} == 1 ]] || { echo 'Ambiguous kernel/DTB'; exit 1; }
    version=${kernels[0]##*/vmlinuz-}
    root_id=$(findmnt -n -o UUID /)
    [[ -n $root_id ]] || exit 1
    python3 /usr/local/lib/gtw360/make-fit.py \
        --kernel "${kernels[0]}" --dtb "${dtbs[0]}" \
        --initrd "/boot/initrd.img-$version" --root "UUID=$root_id" \
        --peripheral 0 --output /boot/fitImageB.new
    mv /boot/fitImageB.new /boot/fitImageB
    systemctl enable gtw360-hid-test.service
    sync
    fw_setenv -c "$cfg" boot_part b
else
    systemctl disable --now gtw360-hid-test.service
    fw_setenv -c "$cfg" boot_part a
fi
sync
echo 'Done. Reboot to apply. Host fallback remains in fitImageA.'
