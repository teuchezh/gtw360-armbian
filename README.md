# Armbian для Geniatech / МТС GTW360

Экспериментальный порт для i.MX6ULL, 512 МБ RAM и 8 ГБ eMMC.
Сохраняет установленный заводской U-Boot. Неофициальная сборка, статус WIP.

## Что проверено на устройстве

- Armbian 26.11.0-trunk, Debian 13 Trixie, Linux 6.18.60-current-imx6.
- Полная загрузка с USB, SSH, Ethernet и повторная перезагрузка.
- USB root на ext4, отдельный FAT-раздел для FIT.
- Wi-Fi сканирует сети 2,4 и 5 ГГц; подключение к точке ещё не проверялось.
- Замена Zigbee от u236: CC2652, Z-Stack 2.7.1 / 20221226, UART 115200.
- Модули UVC, HID и USB mass storage загружаются; configfs доступен.

Bluetooth проверен: оригинальный BCM4345C0.hcd из резервной копии OpenWrt загрузился,
сканирование обнаруживает устройства. Файл прошивки в репозиторий не включён. Для Bluetooth нужны BlueZ и собственный
файл /lib/firmware/brcm/BCM4345C0.hcd из исходной прошивки устройства. Полноценный IP-KVM,
USB OTG с реальным компьютером, HDMI-захват и сопряжение Zigbee пока не проверены.
Armbian установлен на eMMC: FAT 256 МиБ и ext4 на оставшемся месте.
Загрузка и обычная перезагрузка с eMMC без USB проверены. USB-копия сохранена для восстановления.

**Готового релиза образов пока нет.** Проверенная USB-система обновлялась отдельно.
Старые локальные img/xz не содержат исправления tmpfs и не считаются рабочим релизом.

## Сборка ядра

Основа Armbian закреплена на коммите
`18e87d5385f9191419e6afa646080b68fbe7a1d5`.

На поддерживаемом Armbian Debian/Ubuntu-хосте с правами root:

```sh
./scripts/build-kernel.sh CPUTHREADS=8
```

Скрипт получает закреплённый исходный код в sources/armbian, копирует userpatches
и вызывает штатную сборку Armbian. Пакеты появляются в sources/armbian/output/debs/.
В конфигурации явно включены tmpfs, ext4, FAT, FEC/Micrel, ChipIdea host/gadget и UVC.
Отключать tmpfs нельзя: он необходим для systemd.

## Сборка образов — экспериментальный локальный инструмент

Требуются ARM binfmt/QEMU, инструменты сборки Armbian и пакеты
mtools, dosfstools, e2fsprogs, util-linux, u-boot-tools, device-tree-compiler и zstd.
Сборка требует разрешённых mount/chroot; упаковка файловых систем обходится без loop-устройств.

Подготовьте собственные локальные файлы:

- backups/emmc-first-4MiB.bin: первые 4 МиБ основной области eMMC именно вашего GTW360;
- backups/rescue-access.pub: ваш открытый SSH-ключ;
- configs/network.local.env: ваши адрес, шлюз, DNS и MAC по примеру network.example.env.

```sh
source configs/network.local.env
./scripts/build-image.sh CPUTHREADS=8
python3 scripts/verify-armbian-images.py
```

Экспортируется rootfs, затем создаются USB- и eMMC-образы. Параметры сети передаются явно.
Случайный пароль консоли хранится только локально в backups/armbian-root-password.txt.
SSH использует переданный открытый ключ. Нельзя публиковать локальную папку backups.

USB: раздел 1 — ext4 root, раздел 2 — FAT с fitImage-rescue-gtw360.
На проверенном устройстве сохранённая команда U-Boot читает `usb 0:2`.
Заводские настройки других устройств могут отличаться: сначала проверьте fw_printenv.
Одна Netac-флешка не определялась в U-Boot; замена USB DISK 2.0 загрузилась успешно.

eMMC: FAT с fitImageA/fitImageB, затем ext4 root. Образ зависит от собственной
резервной копии boot-prefix и существующих boot0/boot1. Запись на eMMC не автоматизирована.
USB- и eMMC-образы одной сборки имеют одинаковые UUID: одновременно использовать их нельзя.

## FIT и диагностика

scripts/make-fit.py упаковывает kernel, DTB и необязательный initramfs с SHA-256.
FIT загружается заводским U-Boot по адресу 0x88800000, ядро — 0x80800000.
Исходники вспомогательных ARM-утилит находятся в rescue/src.
Для необязательной RAM-диагностики нужен собственный rootfs: см. rescue/README.md.

## Zigbee

configs/zigbee содержит проверенную инициализацию заменённого модуля u236,
udev-псевдоним /dev/zigbee и фрагмент настройки Zigbee2MQTT (`adapter: zstack`).
Штатный gpio-export из OpenWrt в mainline не работает: текущий обходной путь
выставляет boot/reset в высокий уровень и выбирает gpiogrp через pinctrl debugfs.
Прошивка и NVRAM модуля не изменяются. Сам Zigbee2MQTT не устанавливается.
Эти файлы добавляются упаковщиком в новые rootfs; повторная полная сборка ещё не проверена.

## Светодиоды

configs/leds содержит проверенную службу gtw360-leds.service.
Зелёный показывает link и RX/TX eth0; синий — link и RX/TX wlan0.
Янтарный использует триггер kernel panic.
Настройки применяются при старте и включаются упаковщиком новых образов.

## USB gadget — тестовый режим

USB0 соответствует встроенному USB-A; USB1 остаётся host для второго порта.
Linux 6.18.60 с dr_mode=peripheral зарегистрировал UDC ci_hdrc.0.
Тест configs/usb-gadget создаёт клавиатуру /dev/hidg0 и мышь /dev/hidg1.
Тест не отправляет нажатия и движения. Определение устройств на ПК ещё не проверено.
В проверяемой установке слот A сохраняет host-вариант; слот B содержит peripheral-FIT.
Служба теста включается только при наличии UDC. Остановите её перед настройкой KVMD.
Не подключайте обычный A-A до проверки USB Switch и питания VBUS.
BOOT-переключатели и USB Switch — разные узлы; не переводите BOOT в Serial Downloader.

Аппаратное руководство: https://file.geniatech.com/download/Gateway/GTW360_HW_UserGuide_V1.1_EN.pdf
Раздел 3.7 показывает отдельный USB Switch у разъёмов.

## GitHub Actions

Откройте Actions → Build GTW360 kernel → Run workflow.
Workflow собирает только ядро на ubuntu-24.04. Запуск — вручную.
Armbian и Linux закреплены на проверенных коммитах; версия ядра — 6.18.60.
Проверка требует ARM zImage, GTW360 DTB и обязательные параметры, включая tmpfs.
Артефакт gtw360-kernel-<номер> содержит deb-пакеты, SHA256SUMS и BUILD-INFO.json.
Срок хранения — 7 дней. Логи сборки доступны на странице запуска.
Полные образы пока не собираются в Actions.
Рабочие rootfs, ключи, пароли и резервные копии не используются.

## Источники

- https://github.com/armbian/build
- https://community.homed.dev/d/10-zapusk-openwrt-na-domashnem-tsentre-mts-geniatech-gtw360
- https://community.homed.dev/d/65-proshivka-cc2652-v-openwrt
- https://www.zigbee2mqtt.io/guide/adapters/zstack.html

Лицензия исходников проекта: GPL-2.0, см. LICENSE.
