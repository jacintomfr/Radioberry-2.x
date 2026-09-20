# Radioberry Juice firmware — start here

This directory contains the Radioberry Juice host software for Linux and
Windows. It communicates with the radio over USB using FTDI D2XX, loads the
FPGA gateware, and connects the radio to SDR software over the network.

Use this page as a reading guide. The linked documents contain the detailed
commands, requirements, and troubleshooting steps.

## Which document should I read?

| What you want to do | Read this |
| --- | --- |
| Build for Raspberry Pi, Ubuntu, or Windows | [Build guide](BUILD-README.md) |
| Install and run on Linux, including USB access | [Linux installation guide](FTDI-LINUX-README.md) |
| Set up Windows compilers and FTDI drivers | [Windows setup guide](FTDI-WINDOWS-README) |
| Understand the Linux FTDI packages and architectures | [Linux FTDI overview](ftdi/linux/1.4.35/README.md) |

## Raspberry Pi or Ubuntu: suggested reading order

**No separate FTDI download is required for Linux.** D2XX 1.4.35 headers,
libraries and documentation for all included Linux targets are already in
`ftdi/linux/1.4.35/`. The build selects the matching files, and the installer
installs the bundled library with the application.

1. Choose your architecture using the [Linux FTDI overview](ftdi/linux/1.4.35/README.md).
   **A Raspberry Pi running a 64-bit OS uses `aarch64`, also called ARM64.**
   A compatible 32-bit ARMv7 installation uses `armhf`.
2. Follow the [build guide](BUILD-README.md). Building directly on the target
   machine is the simplest way to match its system libraries. Run
   `make -f linux-Makefile` from `juice/firmware`.
3. Follow the [Linux installation guide](FTDI-LINUX-README.md). After building,
   preview with `bash install-linux.sh --dry-run`, then install with
   `sudo bash install-linux.sh`.
4. Review your radio settings, refresh group membership, and reconnect USB
   as described in that guide. Start the installed application with
   `radioberry-juice` as your normal user.

The installer checks USB access and creates missing rules automatically.
Existing rules and settings are preserved. No `--rules` or `--user` option is
needed for a normal installation through `sudo`. A serial filter is optional.

## Windows: installer (recommended)

The easiest way to install on 64-bit Windows is the MSI installer under
[releases](https://github.com/jacintomfr/Radioberry-2.x/releases) (tag
`juice-windows-v1.0.0` or later): `radioberry-juice-<version>-x64.msi`.
It installs `radioberry-juice-x64.exe`, the FPGA gateware, and a default
`radioberry.props` to `Program Files\radioberry-juice\`, with a Start Menu
shortcut. Requires Administrator (it's a per-machine install, same as most
Windows installers).

**The MSI does not include the FTDI CDM driver.** Install that yourself
first, once: download and run FTDI's own driver installer from
[ftdichip.com/drivers/d2xx-drivers](https://ftdichip.com/drivers/d2xx-drivers/),
then run the MSI. This is deliberate, not an oversight: FTDI's own driver
license only permits redistributing the driver "with the Device" (i.e. by
whoever sells the physical Radioberry hardware), and this project isn't a
hardware seller. The installer's first screen explains this, and
`DRIVER-README.txt` (installed alongside the program, also linked from its
Start Menu folder) has the full explanation plus a `pnputil` command to
verify the driver installed correctly.

Building and packaging this installer yourself (e.g. after a code change)
uses the same [WiX Toolset v3](https://wixtoolset.org/) hpsdr-rs itself
builds with:

```powershell
packaging\windows\build-msi.ps1 -Version 1.0.0
```

See `packaging/windows/main.wxs` for the installer definition.

## Windows: building from source

1. Use the [Windows setup guide](FTDI-WINDOWS-README) to install the required
   compiler tools and FTDI driver.
2. Follow the Windows section of the [build guide](BUILD-README.md).
   Use `make -f windows-Makefile ARCH=x64` for 64-bit or `ARCH=x86` for 32-bit.
3. Run the resulting executable from the firmware directory, with the required
   runtime DLLs available and the matching gateware and configuration files.

The Linux installer is for Linux targets only, including when building from
Ubuntu in WSL. Windows uses its own driver installation procedure.

## What is in this directory?

| File or directory | Purpose |
| --- | --- |
| `*.c`, `*.h` | Host application source code and headers |
| `linux-Makefile`, `windows-Makefile` | Platform-specific build instructions; select one with `make -f` |
| [install-linux.sh](install-linux.sh) | Installs a completed Linux build, its local library, launcher, and missing USB rules |
| `packaging/windows/` | MSI installer definition (WiX) and `build-msi.ps1` -- see the Windows installer section above |
| `gateware/CL016/radioberry.rbf`, `gateware/CL025/radioberry.rbf` | FPGA gateware selected by `fpga=CL016` or `fpga=CL025` in `radioberry.props` |
| `radioberry.props` | Configuration template; see the platform instructions for its active location |
| `ftdi/linux/1.4.35/` | Linux D2XX headers, libraries, and original FTDI documentation per architecture |
| `ftdi/windows/cdm-2.12.36.20/` | Windows D2XX headers and import libraries |
| `build/` | Intermediate build files |
| `dist/linux-<architecture>/` | Complete Linux distribution: executable, local FTDI library, gateware, template, documentation, and installer |
| `tests/` | Installer checks using temporary installation directories |

## Build, installation, and runtime

A **build** compiles the application for one operating system and architecture.
An **installation** puts the completed build on the target and configures access
to the radio. **Running** the application then loads the FPGA and handles SDR
communication; the installer does not start the radio or create a boot service.

All bundled Linux targets use D2XX **1.4.35**. Each Linux distribution includes
the same architecture-specific library used during its build, so a separate
system-wide D2XX installation is unnecessary. Windows uses **CDM 2.12.36.20**.

The Linux x86_64 build, ARM64 cross-build, and staged installer checks have
passed. USB operation, automatic interface release, and SDR streaming still
require verification with the actual radio. See the detailed guides for the
current validation limits and configuration paths.
