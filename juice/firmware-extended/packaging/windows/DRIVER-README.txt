radioberry-juice needs the FTDI D2XX driver, installed separately
=====================================================================

This installer does NOT include the FTDI CDM driver package. That is
deliberate, not an oversight: FTDI's own driver license (the terms
embedded as comments in ftdibus.inf, also published at
https://ftdichip.com/driver-licence-terms/) only permits redistributing
the driver "with the Device" -- i.e. by whoever sells the actual
Radioberry hardware. This installer is independent software, not a
hardware seller, so it doesn't redistribute the driver itself.

Before running radioberry-juice.exe, install FTDI's official CDM
driver package yourself, once:

  1. Download the driver installer from FTDI's own site:
     https://ftdichip.com/drivers/d2xx-drivers/
     (look for "CDM Drivers" -- the "setup executable" download)

  2. Run it and follow the prompts.

  3. Connect the Radioberry over USB. Windows should recognize it
     using the driver you just installed.

To verify the driver installed correctly, open PowerShell and run:

  pnputil /enum-drivers | Select-String -Pattern "FTDI" -Context 5,5

You should see entries for ftdibus.inf and ftdiport.inf.

Once the driver is installed, edit radioberry.props (in this program's
install folder) with your callsign/locator and FPGA variant (CL016 or
CL025), then run radioberry-juice.exe.
