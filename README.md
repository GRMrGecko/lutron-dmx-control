This project is designed to control the GRAFIK Eye QS Control panel via the QSE-CI-NWK-E with the serial interface. The project is designed to use the OLA (https://www.openlighting.org/) project to use a DMX device to a network DMX protocol to control the 6 available zones. This project also supports MQTT messaging for Home Assistant support.

I designed this software for use on a Raspberry Pi using the 2019-07-10-raspbian-buster-lite release and OLA at https://github.com/OpenLightingProject/ola/tree/dc40569a7ef2512c7c9459a94c9dc4292d809262 compiled and installed using instructions at https://www.openlighting.org/ola/linuxinstall/

# Installation

1. Decide if you want Home Assistant support, if you do not, you can skip to step 5.
2. If you do not already have an home assistant setup, you can view https://www.home-assistant.io/installation/ or use the base configurations in the `Home Assistant` directory to use my home assistant docker setup. The base configuration is designed for the HUSBZB-1 USB adapter, which you can use `ls -lah /dev/serial/by-id/` to see which ttyUSB interfaces are which, and get the correct serial number for your device.
3. If you don't have MQTT setup, you can follow guide at https://cyan-automation.medium.com/setting-up-mqtt-and-mosquitto-in-home-assistant-20eb810a91e6 or use my base configurations in the `Home Assistant` directory to configure mosquitto. Once you setup a username/password in the pwfile, use `mosquitto_passwd -U pwfile` to encrypt the password.
4. Edit the `lutron-dmx-control.py` file to make sure MQTT is enabled, pointed to the proper server, and has the correct password configured.
5. If you are not planning on using MQTT/Home Assistant, you can edit `lutron-dmx-control.py` to change `MQTT_ENABLED` from True to False.
6. Update the serial port for the QSE NWK in `lutron-dmx-control.py`, you can use `ls -lah /dev/serial/by-id/` to determine the device id.
7. Run the bash script install.sh to install services for olad and `lutron-dmx-control.py`.

```bash
sudo bash ./install.sh
```

# Configuration
Once services are installed we need to stop the olad service to edit configuration files with `sudo systemctl start olad@pi`. We can then configure ola by editing the configuration files in `.ola/` to disable the modules which are not used as some of them will take the serial device. Once configured, run `sudo systemctl start olad@pi` and visit the raspberry pi's IP address at port 9090 in your browser to configure the DMX universe you are going to use. Once configured, you can then test this software by changing the configuration portion of the code.

Trick to disable all modules except the one you are using.

```bash
sed -i '/enabled\s=/c\enabled = false' ~/.ola/*.conf
sed -i '/enabled\s=/c\enabled = true' ~/.ola/ola-e131.conf
```

# Home Assistant MQTT config

If you have your own Home Assistant install, the configuration for this project is below.

```yaml
light:
  - platform: mqtt
    schema: json
    name: lutron_qse_nwk
    state_topic: "lutron/qse-nwk"
    command_topic: "lutron/qse-nwk/set"
    brightness: true
    color_mode: true
    supported_color_modes: ["brightness"]
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