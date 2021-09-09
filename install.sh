#!/bin/bash

USER=$(whoami)
if [ "$USER" != "root" ]; then
    echo "Please use sudo with this install script to ensure right permissions for installation."
    exit 1
fi

# Get the script directory.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd $SCRIPT_DIR

# Install Python/needed modules.
apt install -y python3-pip python3-serial python3
pip3 install ola
pip3 install paho-mqtt

cp lutron-dmx-control.py /home/pi/lutron-dmx-control.py
chown pi: /home/pi/lutron-dmx-control.py

# Copy lutron-dmx-control@.service and olad@.service to /etc/systemd/system/ and run the following to enable/start.
cp olad@.service /etc/systemd/system/
cp lutron-dmx-control@.service /etc/systemd/system/

systemctl daemon-reload
systemctl enable olad@pi
systemctl start olad@pi
systemctl enable lutron-dmx-control@pi
systemctl start lutron-dmx-control@pi