This project is designed to control the GRAFIK Eye QS Control panel via the QSE-CI-NWK-E with the serial interface. The project is designed to use the OLA (https://www.openlighting.org/) project to use either a DMX device to a network DMX protocol to control the 6 available zones.

I designed this software for use on a Raspberry Pi using the 2019-07-10-raspbian-buster-lite release and OLA at https://github.com/OpenLightingProject/ola/tree/dc40569a7ef2512c7c9459a94c9dc4292d809262 compiled and installed using instructions at https://www.openlighting.org/ola/linuxinstall/

# Configuration
Once OLA is installed, run it using `olad -l 3` and then edit the configuration files in `.ola/` to disable the modules which are not used as some of them will take the serial device. Once configured, run `olad -l 3` again and visit the raspberry pi's IP address at port 9090 in your browser to configure the DMX universe you are going to use. Once configured, you can then test this software by changing the configuration portion of the code.

Trick to disable all modules except the one you are using.

```bash
sed -i '/enabled\s=/c\enabled = false' ~/.ola/*.conf
sed -i '/enabled\s=/c\enabled = true' ~/.ola/ola-e131.conf
```

# Installation

Install Python/needed modules.

```bash
apt install python3-pip python3-serial
pip3 install ola
```

Copy lutron-dmx-control@.service and olad@.service to /etc/systemd/system/ and run the following to enable/start.

```bash
systemctl daemon-reload
systemctl enable olad@pi
systemctl start olad@pi
systemctl enable lutron-dmx-control@pi
systemctl start lutron-dmx-control@pi
```

# Recommend

Enable watchdog on the Raspberry Pi to auto reboot upon system crashes.

Edit `/boot/config.txt` and add under the `[all]` section.
```
watchdog=on
```

Edit `/etc/systemd/system.conf` and uncomment `RuntimeWatchdogSec` and set it as follows.
```
RuntimeWatchdogSec=10s
```

After configuring, reboot.