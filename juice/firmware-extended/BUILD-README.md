# Building Radioberry Juice for Linux and Windows

Run the build commands from `juice/firmware`, the directory containing
`linux-Makefile` and `windows-Makefile`. The `-f` option selects the Makefile.
There is no default `Makefile`, so always specify `-f`.

## Raspberry Pi with 64-bit Raspberry Pi OS or Ubuntu

**All required Linux FTDI files are included in this repository.** No separate
FTDI download or driver package installation is needed. The build uses the
D2XX 1.4.35 headers and libraries in `ftdi/linux/1.4.35/` for the selected target.

Prefer building directly on the Pi. This uses the compiler and system
libraries of the machine that will run the program.

1. Check the userspace architecture:

   ```bash
   dpkg --print-architecture
   ```

   For 64-bit Raspberry Pi Linux, expect `arm64`. The corresponding FTDI
   directory is **`aarch64`**, another name for the same 64-bit ARM architecture.

2. Install the build tools:

   ```bash
   sudo apt update
   sudo apt install build-essential
   ```

3. Go to `juice/firmware` in your checkout and build:

   ```bash
   make -f linux-Makefile info
   make -f linux-Makefile -j2
   ```

   The Makefile detects the architecture using `gcc -dumpmachine`.
   You can also select it explicitly:

   ```bash
   make -f linux-Makefile ARCH=aarch64 -j2
   ```

4. The output is in `dist/linux-aarch64/`:

   ```text
   install-linux.sh
   radioberry-juice
   radioberry.props
   gateware/CL016/radioberry.rbf
   gateware/CL025/radioberry.rbf
   lib/libftd2xx.so
   ftdi/                 # FTDI documentation and licence text
   ```

5. Before running, set up USB access and check the configuration as described
   below. Then start the program from the distribution directory:

   ```bash
   cd dist/linux-aarch64
   ./radioberry-juice
   ```

The bundled D2XX 1.4.35 library is located next to the program using
`$ORIGIN/lib`. This build does not require a system-wide D2XX installation.

To install the built distribution on the Pi, use the included script:

```bash
bash install-linux.sh --dry-run
sudo bash install-linux.sh
```

This installs the application and launcher and creates missing USB rules.
Existing rules are preserved and the
invoking user is detected automatically; `--serial` is an optional filter for
new rules. See the
[installation script instructions](FTDI-LINUX-README.md#installation-script-recommended)
for the full procedure, including automatic interface release after reconnecting.

## Other Linux targets

Install `build-essential` on these systems as well, and build from
`juice/firmware`. For a native build, use `make -f linux-Makefile -j2`.

| System | `dpkg --print-architecture` | Explicit build | Output |
| --- | --- | --- | --- |
| Raspberry Pi, 64-bit Linux | `arm64` | `make -f linux-Makefile ARCH=aarch64` | `dist/linux-aarch64/` |
| Compatible ARMv7 system, 32-bit Linux | `armhf` | `make -f linux-Makefile ARCH=armhf` | `dist/linux-armhf/` |
| Ubuntu on Intel/AMD, 64-bit | `amd64` | `make -f linux-Makefile ARCH=x86_64` | `dist/linux-x86_64/` |
| Intel/AMD, 32-bit Linux userspace | `i386` | `make -f linux-Makefile ARCH=x86_32` | `dist/linux-x86_32/` |

The `armhf` directory contains the ARMv7 hard-float library. It is not suitable
for ARMv6-only Pi models such as the original Pi 1 and Pi Zero/Zero W.
A 64-bit processor running a 32-bit OS requires a 32-bit build.

`ARCH` selects the FTDI directory and output directories; it does not change
the compiler. Choose a compiler that builds for the same architecture.
When changing compilers or compiler flags within a target, clean it first:

```bash
make -f linux-Makefile ARCH=aarch64 clean
```

This removes only the selected target's Linux build and distribution directories.
Save any custom changes in the distribution directory before cleaning it.

## Cross-compiling for Raspberry Pi 64-bit from Ubuntu or WSL

On Ubuntu x86_64, including Ubuntu in WSL on Windows:

```bash
sudo apt update
sudo apt install build-essential gcc-aarch64-linux-gnu
make -f linux-Makefile ARCH=aarch64 CC=aarch64-linux-gnu-gcc -j2
```

Copy the entire `dist/linux-aarch64/` directory to the Pi and run the program
from that directory. An ARM64 program cannot run directly on an x86_64 Ubuntu
PC. The Pi must also have compatible system libraries: a build on a newer
Ubuntu release may require a newer glibc than the Pi provides. Building
natively on the Pi avoids this version mismatch.

## Linux: USB access and configuration before running

See [FTDI-LINUX-README.md](FTDI-LINUX-README.md) for USB diagnostics, access
permissions, and releasing the FTDI interface from `ftdi_sio`.
Install or copy the complete distribution directory as described there, and
verify that `ldd` resolves D2XX from its local `lib/` directory. No system-wide
D2XX installation is required. USB permissions and interface release remain
separate setup steps on the target machine.

On Linux, the current firmware reads settings from this path in the invoking
user's own home directory:

```text
$HOME/.radioberry/radioberry.props
```

The copy in `dist/` is a template and is not loaded automatically on Linux.
Create the directory if needed and copy the template only if no
configuration exists yet (run from `juice/firmware`):

```bash
mkdir -p ~/.radioberry
cp -n radioberry.props ~/.radioberry/radioberry.props
nano ~/.radioberry/radioberry.props
```

Enter your own details. No `sudo` is needed -- this lives under your own
account, so it works the same whatever your username is. `install-linux.sh`
and the `.deb` package set this up automatically for the installing user.
The selected gateware is read from `gateware/` in the current working directory, so start from
the distribution directory. Any custom gateware version must match your FPGA.

## Windows: 64-bit and 32-bit

Use PowerShell or the Windows command prompt with GNU Make and the appropriate
MinGW-w64 G++ compiler in `PATH`. The Windows Makefile uses Windows `cmd.exe`
commands. Do not use a Linux shell for this Makefile.

See [FTDI-WINDOWS-README](FTDI-WINDOWS-README) for installation instructions
for MSYS2, the toolchains, and the FTDI D2XX Windows driver.

Check your tools:

```powershell
make --version
x86_64-w64-mingw32-g++ --version
```

Build for 64-bit Windows, the default:

```powershell
make -f windows-Makefile
```

Or select the target explicitly:

```powershell
make -f windows-Makefile ARCH=x64
make -f windows-Makefile ARCH=x86
```

For x86, `i686-w64-mingw32-g++` must be available. If GNU Make is named
`mingw32-make` on your system, replace `make` with `mingw32-make`.

| Target | FTDI library | Output in `juice/firmware` |
| --- | --- | --- |
| x64 | `ftdi/windows/cdm-2.12.36.20/lib/x64/ftd2xx.lib` | `radioberry-juice-x64.exe` |
| x86 | `ftdi/windows/cdm-2.12.36.20/lib/x86/ftd2xx.lib` | `radioberry-juice-x86.exe` |

The Windows build also creates `dist/windows-x64/` or `dist/windows-x86/`
with the executable, `radioberry.props`, and both FPGA
variants under `gateware/CL016/` and `gateware/CL025/`. Start from that
distribution directory. The appropriate FTDI D2XX runtime and MinGW runtime
DLLs must still be installed or available through `PATH`; they are not copied
into the distribution.

For both Windows and Linux, set `fpga=CL016` or `fpga=CL025` in
`radioberry.props` before starting. On Linux, an existing
`$HOME/.radioberry/radioberry.props` (for whichever user runs the program)
takes precedence over the file in the working directory. The selected file
under `gateware/` is loaded
automatically. See [gateware notes](gateware/README.md).

Clean an individual Windows target:

```powershell
make -f windows-Makefile clean-x64
make -f windows-Makefile clean-x86
```

## Verification

Linux x86_64 and an ARM64 cross-build were compiled and linked with GCC in
Ubuntu/WSL. The existing source code still produces compiler warnings,
including printf format mismatches and possible HTTP message truncation.
A successful build is not a hardware test: USB access, FPGA loading, and SDR
streaming still need testing on the target machine. The 32-bit Linux targets
were not built during this verification.

For FTDI target details, see the [Linux FTDI overview](ftdi/linux/1.4.35/README.md).
Ubuntu packages: [build-essential](https://packages.ubuntu.com/noble/build-essential)
and [gcc-aarch64-linux-gnu](https://packages.ubuntu.com/noble/gcc-aarch64-linux-gnu).
