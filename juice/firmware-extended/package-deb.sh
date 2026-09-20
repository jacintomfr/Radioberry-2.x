#!/bin/bash
# Build the Linux firmware and package it as the radioberry-juice .deb.
# Run from the repository root (where linux-Makefile lives).
set -euo pipefail

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$script_dir"

arch_deb=$(dpkg --print-architecture)
case "$arch_deb" in
    amd64) arch_make=x86_64 ;;
    i386) arch_make=x86_32 ;;
    arm64) arch_make=aarch64 ;;
    armhf) arch_make=armhf ;;
    *) die "Unsupported architecture: $arch_deb" ;;
esac

dist_dir="dist/linux-$arch_make"

echo "== Building ($arch_make) =="
make -f linux-Makefile ARCH="$arch_make" -j"$(nproc)"

version=$(awk -F': ' '/^Version:/{print $2; exit}' packaging/debian/control)
[[ -n $version ]] || die "Could not read Version from packaging/debian/control"

work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
stage="$work/stage"

echo "== Staging into $stage =="
bash "$dist_dir/install-linux.sh" --source "$dist_dir" --destdir "$stage"

echo "== Assembling DEBIAN control files =="
install -d -m 755 "$stage/DEBIAN"
sed "s/^Architecture:.*/Architecture: $arch_deb/" packaging/debian/control > "$stage/DEBIAN/control"
install -m 755 packaging/debian/postinst "$stage/DEBIAN/postinst"
install -m 644 packaging/debian/conffiles "$stage/DEBIAN/conffiles"
install -D -m 644 packaging/debian/copyright "$stage/usr/share/doc/radioberry-juice/copyright"

out="radioberry-juice_${version}_${arch_deb}.deb"
echo "== Building $out =="
dpkg-deb --build --root-owner-group "$stage" "$out"

echo "Done: $script_dir/$out"
