#!/bin/bash
# Install an existing Linux build; never build or start the radio as root.
set -euo pipefail
export LC_ALL=C

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
usage() {
    cat <<'HELP'
Usage: bash install-linux.sh [options]
  --source DIR   Distribution directory (default: dist/linux-<native arch>)
  --serial TEXT  Optional serial filter for newly created rules
  --user NAME    Add this existing user to the radioberry group
                 Default: the user who invoked sudo
  --dry-run      Validate inputs and print the plan without changing anything
  --destdir DIR  Stage files under an absolute directory for packaging/testing;
                 do not change host groups or reload host udev
  --help         Show this help

Installs to /opt/radioberry-juice with a launcher in /usr/local/bin.
Preserves <user's home>/.radioberry/radioberry.props if it already exists.
USB rules, helper and group access are checked during every installation.
Stop the radio before updating. New USB rules target 0403:6010 by default.
Existing 99-radioberry.rules and its helper are kept, including serial filters.
The known old 99-ftdisio.rules entry is backed up and replaced automatically.
HELP
}

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source_dir= serial= install_user=${SUDO_USER:-${USER:-}} destdir=
dry_run=0
while (($#)); do
    case "$1" in
        --source|--serial|--user|--destdir)
            (($# >= 2)) && [[ -n $2 && $2 != --* ]] || die "Missing value for $1"
            case "$1" in
                --source) source_dir=$2 ;;
                --serial) serial=$2 ;;
                --user) install_user=$2 ;;
                --destdir) destdir=$2 ;;
            esac
            shift 2 ;;
        --dry-run) dry_run=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) die "Unknown option: $1" ;;
    esac
done

[[ $(uname -s) == Linux ]] || die 'Run this script on Linux.'
for tool in dpkg readelf install realpath cmp; do
    command -v "$tool" >/dev/null || die "Required command not found: $tool"
done
case "$(dpkg --print-architecture)" in
    amd64) arch=x86_64; elf_class=ELF64; machine='Advanced Micro Devices X86-64' ;;
    i386) arch=x86_32; elf_class=ELF32; machine='Intel 80386' ;;
    arm64) arch=aarch64; elf_class=ELF64; machine=AArch64 ;;
    armhf) arch=armhf; elf_class=ELF32; machine=ARM
        # This project's armhf library needs ARMv7 even when the OS says armhf.
        case "$(uname -m)" in armv7*|armv8*|aarch64) ;; *) die 'The armhf package requires an ARMv7-compatible CPU.' ;; esac ;;
    *) die 'Unsupported Debian/Ubuntu userspace architecture.' ;;
esac
if [[ -z $source_dir ]]; then
    if [[ -f $script_dir/radioberry-juice ]]; then source_dir=$script_dir
    else source_dir=$script_dir/dist/linux-$arch
    fi
fi
source_dir=$(realpath -e -- "$source_dir") || die 'Distribution directory not found; build first.'
required=(radioberry-juice radioberry.props lib/libftd2xx.so
          gateware/CL016/radioberry.rbf gateware/CL025/radioberry.rbf
          ftdi/README.pdf ftdi/release-notes.txt ftdi/SOURCE.txt ftdi/ftd2xx.h)
for file in "${required[@]}"; do
    [[ -f $source_dir/$file && ! -L $source_dir/$file ]] || die "Missing or symlinked input: $file"
done
for file in radioberry-juice lib/libftd2xx.so; do
    header=$(readelf -h "$source_dir/$file")
    [[ $header == *"$elf_class"* && $header == *"Machine:"*"$machine"* ]] || die "Wrong architecture: $file (expected $arch)"
done
dynamic=$(readelf -d "$source_dir/radioberry-juice")
[[ $dynamic == *'[$ORIGIN/lib]'* && $dynamic == *'[libftd2xx.so]'* ]] || die 'Executable must use the bundled D2XX library through $ORIGIN/lib.'

if [[ -n $destdir ]]; then
    [[ $destdir == /* ]] || die '--destdir must be absolute.'
    destdir=$(realpath -m -- "$destdir")
    [[ $destdir != / ]] || die '--destdir must not be /; omit it for a live installation.'
elif (( ! dry_run && EUID != 0 )); then
    die 'Use sudo for a live installation, or --dry-run to preview it.'
fi
app_dir=$destdir/opt/radioberry-juice
launcher=$destdir/usr/local/bin/radioberry-juice
rule_file=$destdir/etc/udev/rules.d/99-radioberry.rules
helper=$destdir/usr/local/libexec/radioberry-usb-unbind
legacy_file=$destdir/etc/udev/rules.d/99-ftdisio.rules
[[ $source_dir != "$app_dir" ]] || die 'Source and installation directory must differ.'

[[ -z $serial || $serial =~ ^[A-Za-z0-9_-]+$ ]] || die '--serial may contain only letters, digits, underscores or hyphens.'
[[ -n $install_user && $install_user != root ]] || die 'Specify the normal login account with --user.'
[[ $install_user =~ ^[a-zA-Z_][a-zA-Z0-9_-]*[$]?$ ]] || die 'Invalid login account name.'
config_dir=
if [[ -z $destdir ]]; then
    for tool in getent groupadd usermod udevadm; do
        command -v "$tool" >/dev/null || die "Required command not found: $tool"
    done
    install_user_home=$(getent passwd "$install_user" | cut -d: -f6) || die "Unknown user: $install_user"
    [[ -n $install_user_home && $install_user_home == /* ]] || die "Could not determine a home directory for $install_user"
    config_dir=$install_user_home/.radioberry
fi

# Reject symlinked destinations before any privileged writes.
check_destination() {
    local path=$1
    while [[ $path != / ]]; do
        [[ ! -L $path ]] || die "Symlinked destination: $path"
        path=$(dirname -- "$path")
    done
    [[ ! -d $1 ]] || die "Expected a file destination: $1"
}
for file in "${required[@]}"; do check_destination "$app_dir/$file"; done
check_destination "$launcher"
[[ -z $config_dir ]] || check_destination "$config_dir/radioberry.props"
check_destination "$rule_file"
check_destination "$helper"
legacy_replace=0
legacy_keep=()
if [[ -e $legacy_file || -L $legacy_file ]]; then
    check_destination "$legacy_file"
    [[ -f $legacy_file && -r $legacy_file ]] || die "Cannot read old USB rules: $legacy_file"
    known_legacy=$(cat <<'LEGACY'
ACTION=="add", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6010", MODE="0666", RUN+="/bin/sh -c 'rmmod ftdi_sio && rmmod usbserial'"
LEGACY
)
    known_legacy=${known_legacy//[[:space:]]/}
    while IFS= read -r line || [[ -n $line ]]; do
        normalized=${line//$'\xc2\xa0'/ }
        normalized=${normalized//[[:space:]]/}
        normalized=${normalized//\\_/_}
        if [[ $normalized == "$known_legacy" ]]; then
            legacy_replace=1
        else
            if [[ -n $normalized && $normalized != \#* && ( $normalized == *rmmod* || $normalized == *modprobe*-r* ) ]]; then
                die "An unrecognized driver-removal rule exists in $legacy_file. Open it with sudo nano, remove only the obsolete Radioberry rule, then run this installer again. Other rules must be kept."
            fi
            legacy_keep+=("$line")
        fi
    done < "$legacy_file"
fi
if [[ ! -e $rule_file && -e $helper && -z $serial ]]; then
    if grep -Fq '[[ $# == 2 &&' "$helper"; then
        die 'Existing USB helper requires a serial. Use --serial for the new rule, or update that helper first.'
    fi
fi

printf 'Architecture: %s\nSource: %s\nInstall: %s\nLauncher: %s\n' "$arch" "$source_dir" "$app_dir" "$launcher"
if [[ -n $config_dir ]]; then
    printf 'Configuration: %s (preserve if present)\n' "$config_dir/radioberry.props"
else
    printf 'Configuration: created per-user under ~/.radioberry/radioberry.props at package-install time\n'
fi
if ((legacy_replace)); then
    printf 'Old Radioberry USB rule found. Installation will back it up and remove the obsolete entry; other entries are kept.\n'
    printf 'The replacement USB setup below will be used. No manual removal is needed.\n'
fi
if [[ -e $rule_file ]]; then
    printf 'USB rules: keep existing %s (existing device filters remain active)\n' "$rule_file"
    [[ -z $serial ]] || printf 'Existing rules are preserved; --serial does not modify them.\n'
else
    printf 'USB rules: create %s for 0403:6010, serial %s\n' "$rule_file" "${serial:-all}"
fi
if [[ -e $helper ]]; then printf 'USB helper: keep existing %s\n' "$helper"
else printf 'USB helper: create %s\n' "$helper"; fi
printf 'USB access: ensure group radioberry includes user %s\n' "$install_user"
if [[ -n $destdir ]]; then printf 'Staging only: no host group changes or udev reload.\n'; fi
if ((dry_run)); then printf 'Dry run complete; no changes made.\n'; exit 0; fi

umask 022
# Existing installed files receive one .previous backup; settings are preserved.
copy_file() {
    install -D -m "$3" -b --suffix=.previous -- "$1" "$2"
}
for file in "${required[@]}"; do
    mode=644
    [[ $file != radioberry-juice ]] || mode=755
    copy_file "$source_dir/$file" "$app_dir/$file" "$mode"
done
cmp -- "$source_dir/lib/libftd2xx.so" "$app_dir/lib/libftd2xx.so"
if [[ -n $config_dir ]]; then
    install -d -m 755 -o "$install_user" -g "$(id -gn "$install_user")" -- "$config_dir"
    if [[ ! -e $config_dir/radioberry.props ]]; then
        install -m 644 -o "$install_user" -g "$(id -gn "$install_user")" -- "$source_dir/radioberry.props" "$config_dir/radioberry.props"
    fi
fi

temporary=$(mktemp -d)
trap 'rm -rf -- "$temporary"' EXIT
cat > "$temporary/launcher" <<'LAUNCHER'
#!/bin/bash
set -e
cd /opt/radioberry-juice
exec ./radioberry-juice "$@"
LAUNCHER
copy_file "$temporary/launcher" "$launcher" 755

cat > "$temporary/unbind" <<'UNBIND'
#!/bin/bash
# Called after ftdi_sio binds; recheck the device before releasing an interface.
set -euo pipefail
[[ $# == 1 || $# == 2 ]] || exit 1
[[ $1 =~ ^[0-9]+-[0-9]+(\.[0-9]+)*:[0-9]+\.[0-9]+$ ]] || exit 1
[[ $# == 1 || $2 =~ ^[A-Za-z0-9_-]+$ ]] || exit 1
interface=/sys/bus/usb/devices/$1
device=/sys/bus/usb/devices/${1%%:*}
[[ -r $device/idVendor && -r $device/idProduct ]] || exit 0
[[ $(< "$device/idVendor") == 0403 && $(< "$device/idProduct") == 6010 ]] || exit 0
if [[ $# == 2 ]]; then
[[ -r $device/serial && $(< "$device/serial") == "$2" ]] || exit 0
fi
[[ $(readlink -f "$interface/driver") == /sys/bus/usb/drivers/ftdi_sio ]] || exit 0
printf '%s' "$1" > /sys/bus/usb/drivers/ftdi_sio/unbind
UNBIND
device_filter= interface_filter= helper_argument=
if [[ -n $serial ]]; then
    device_filter=", ATTR{serial}==\"$serial\""
    interface_filter=", ATTRS{serial}==\"$serial\""
    helper_argument=" $serial"
fi
cat > "$temporary/rules" <<RULES
# Radioberry Juice: USB permissions and automatic interface release.
SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTR{idVendor}=="0403", ATTR{idProduct}=="6010"$device_filter, GROUP="radioberry", MODE="0660"
ACTION=="bind", SUBSYSTEM=="usb", DRIVER=="ftdi_sio", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6010"$interface_filter, RUN+="/usr/local/libexec/radioberry-usb-unbind %k$helper_argument"
RULES
rules_changed=0
if [[ ! -e $helper ]]; then
    install -D -m 755 -- "$temporary/unbind" "$helper"
    rules_changed=1
fi
if [[ -z $destdir ]]; then
    if ! getent group radioberry >/dev/null; then groupadd radioberry; fi
    if [[ " $(id -nG "$install_user") " != *' radioberry '* ]]; then
        usermod -aG radioberry "$install_user"
    fi
fi
if [[ ! -e $rule_file ]]; then
    install -D -m 644 -- "$temporary/rules" "$rule_file"
    rules_changed=1
fi
if ((legacy_replace)); then
    # Keep an independent backup on every migration; do not overwrite old backups.
    legacy_backup=$(mktemp "$legacy_file.backup.XXXXXX")
    cp -p -- "$legacy_file" "$legacy_backup"
    : > "$temporary/legacy-rules"
    if ((${#legacy_keep[@]})); then
        printf '%s\n' "${legacy_keep[@]}" > "$temporary/legacy-rules"
    fi
    install -m 644 -- "$temporary/legacy-rules" "$legacy_file"
    printf 'Removed the old Radioberry rule. Backup: %s\n' "$legacy_backup"
    rules_changed=1
fi
if [[ -z $destdir ]] && ((rules_changed)); then udevadm control --reload-rules; fi
printf 'Log out and back in, then reconnect the Radioberry to apply group access and interface release.\n'
if [[ -n $config_dir ]]; then
    printf 'Installation complete. Review %s/radioberry.props, then run radioberry-juice as your normal user.\n' "$config_dir"
else
    printf 'Installation complete.\n'
fi
printf 'The program has not been started. Verify its library with ldd /opt/radioberry-juice/radioberry-juice.\n'
