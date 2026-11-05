function custom_kernel_config__gtw360() {
    opts_n+=(ARCH_VIRT ARCH_SUNPLUS ARCH_BCM ARCH_EXYNOS ARCH_HIGHBANK ARCH_MESON)
    opts_n+=(ARCH_MMP ARCH_MVEBU ARCH_OMAP ARCH_OMAP3 ARCH_OMAP4 ARCH_QCOM)
    opts_n+=(ARCH_ROCKCHIP ARCH_STI ARCH_STM32 ARCH_SUNXI ARCH_TEGRA ARCH_VEXPRESS ARCH_ZYNQ)
    opts_n+=(SOC_IMX50 SOC_IMX51 SOC_IMX53 SOC_IMX6Q SOC_IMX6SL SOC_IMX6SLL SOC_IMX6SX)
    opts_n+=(SOC_LS1021A SOC_IMX7D SOC_IMX7ULP)
    opts_n+=(KUNIT DRM SOUND PCI USB_GSPCA VIDEO_VIVID VIDEO_VIM2M)
    opts_n+=(MEDIA_ANALOG_TV_SUPPORT MEDIA_DIGITAL_TV_SUPPORT MEDIA_RADIO_SUPPORT MEDIA_SDR_SUPPORT MEDIA_TEST_SUPPORT)
    opts_y+=(SOC_IMX6UL FEC PHYLIB MICREL_PHY USB_EHCI_HCD)
    opts_y+=(MMC MMC_BLOCK MMC_SDHCI MMC_SDHCI_PLTFM MMC_SDHCI_ESDHC_IMX)
    opts_y+=(EXT4_FS VFAT_FS DEVTMPFS DEVTMPFS_MOUNT)
    opts_y+=(SHMEM TMPFS TMPFS_POSIX_ACL TMPFS_XATTR)
    opts_y+=(USB USB_GADGET USB_CHIPIDEA USB_CHIPIDEA_IMX)
    opts_y+=(USB_CHIPIDEA_UDC USB_CHIPIDEA_HOST USB_MXS_PHY)
    opts_m+=(USB_CONFIGFS)
    opts_y+=(USB_CONFIGFS_F_HID USB_CONFIGFS_MASS_STORAGE USB_CONFIGFS_ACM)
    opts_y+=(MEDIA_SUPPORT MEDIA_CAMERA_SUPPORT MEDIA_USB_SUPPORT)
    opts_m+=(USB_VIDEO_CLASS)
}

function pre_umount_final_image__gtw360_fit() {
    local boot_dir="${MOUNT}/boot"
    local root_id
    root_id=$(awk '$2 == "/" {print $1; exit}' "${MOUNT}/etc/fstab")
    [[ -n "$root_id" ]] || exit_with_error "GTW360: root filesystem identifier missing"
    local kernel_file initrd_file dtb_file
    kernel_file=$(find "$boot_dir" -maxdepth 1 -type f -name 'vmlinuz-*' | sort -V | tail -1)
    initrd_file=$(find "$boot_dir" -maxdepth 1 -type f -name 'initrd.img-*' | sort -V | tail -1)
    dtb_file=$(find -L "$boot_dir" -type f -name 'imx6ull-gtw360.dtb' | head -1)
    [[ -n "$kernel_file" && -n "$initrd_file" && -n "$dtb_file" ]] || exit_with_error "GTW360: boot files missing"
    run_host_command_logged python3 "${USERPATCHES_PATH}/tools/make-fit.py" \
        --kernel "$kernel_file" --dtb "$dtb_file" --initrd "$initrd_file" \
        --root "$root_id" --output "$boot_dir/fitImageA"
    run_host_command_logged cp "$boot_dir/fitImageA" "$boot_dir/fitImageB"
}

function pre_prepare_partitions__gtw360_export_rootfs() {
    [[ "${GTW360_EXPORT_ROOTFS:-no}" == yes ]] || return 0
    [[ -n "${GTW360_ROOTFS_ARCHIVE:-}" ]] || exit_with_error "GTW360_ROOTFS_ARCHIVE missing"
    mkdir -p "$(dirname "${GTW360_ROOTFS_ARCHIVE}")"
    umask 077
    run_host_command_logged tar --numeric-owner --xattrs --acls --one-file-system \
        --zstd -C "${SDCARD}" -cf "${GTW360_ROOTFS_ARCHIVE}" .
    display_alert "GTW360 rootfs exported for filesystem image packaging" "${GTW360_ROOTFS_ARCHIVE}" "info"
    exit 0
}
