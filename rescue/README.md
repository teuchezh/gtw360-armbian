# Optional RAM rescue

The builder requires your own ARM hard-float rescue rootfs via --rescue-rootfs.
No device rootfs, keys or binary firmware are distributed here.
Adapt init.template with your network settings and install it as rootfs/init.
Supply BusyBox applets, Dropbear, compatible libraries, your authorized public key,
and compile src/watchdog.c as usr/sbin/rescue-watchdog with arm-linux-gnueabihf-gcc -static.
Use scripts/make-rescue.py with the matching kernel and DTB packages.
The template keeps eMMC unmounted. Password authentication is disabled.
