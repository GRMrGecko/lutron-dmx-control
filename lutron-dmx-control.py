# lutron-dmx-control
#
# Copyright (c) 2019, Mr. Gecko's Media (James Coleman)
# All rights reserved.
#
#  Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products
#    derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
#    INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
#    ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
#    SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
#    LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
#    STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
#    ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

from ola.ClientWrapper import ClientWrapper
import serial
import io
import _thread
import threading
import time
import random
import json

from paho.mqtt import client as mqtt_client
# Documentation
# This program is designed to use the Open Lighting Arcretechture (OLA) to receive a DMX signal
#  and translate to commands to control the 6 dimiable zones on the Lutron GRAFIK Eye QS Control panel
#  through the use of a QSE-CI-NWK-E. This program uses the serial port for reliability.

# Configuration
# Serial port device to use to communicate with Lutron's QSE NWK.
QSE_NWK_DEVICE = "/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller-if00-port0"
# Set baud rate on Lutron's QSE NWK.
QSE_NWK_BAUD = 115200
# Number of zones on GRAFIK Eye QS Control panel
QSE_ZONES = 6
# DMX Universe in OLA that is used.
DMX_UNIVERSE = 3
# The starting address.
DMX_START_ADDRESS = 0

#Verbosity
VERBOSE=1

# Variables used at run time, do not adjust.
serialSession = None
zoneValues = []
sentValues = []
sendAllDataThisTime = True
controlDisabled = False
lastDMXUniverseUpdate = 0

# To prevent data from overlapping which is known to crash the QSE NWK, we implement a thread lock which must be released before being obtained.
dataLock = threading.Lock()

# To prevent data from overlapping which is known to crash the QSE NWK, we implement a thread lock which must be released before being obtained.
sendAllDataThisTImeLock = threading.Lock()

# MQTT Configurations
MQTT_ENABLED = True
MQTT_BROKER = '127.0.0.1'
MQTT_PORT = 1883
MQTT_TOPIC = "lutron/qse-nwk"
MQTT_TOPIC_SET = MQTT_TOPIC + "/set"
MQTT_CLIENT_ID = f'lutron-qse-nwk-{random.randint(0, 1000)}'
MQTT_USERNAME = 'mqtt'
MQTT_PASSWORD = 'mqtt_password_placeholder'

# MQTT light state
mqttLightState = "OFF"
mqttLightBrightness = 0
mqttSentLightState = ""
mqttSentLightBrightness = 0

# MQTT state values
MQTT_LIGHT_ON = "ON"
MQTT_LIGHT_OFF = "OFF"

# MQTT Connection
mqtt_conn = None

# This fucnction translates the 0-255 signal from DMX to 0.00 to 100.00 signal used by Lutron,
#  and it sends the appropiate command to the QSE NWK to change the brightness level of a zone.
def qse_send_zone_value(zone, value):
    global serialSession, VERBOSE

    # Translate to the command.
    command = "#DEVICE,1,%d,14,%.2f,00:00" % (zone,round((value/255.00)*100,2))
    if VERBOSE>=1:
        print(command)

    # Send to the QSE NWK.
    serialSession.write(bytes(command+"\n\r", 'utf-8'))

# This function receives data when a DMX update occurs.
def dmx_universe_update(data):
    global dataLock, zoneValues, lastDMXUniverseUpdate, QSE_ZONES, VERBOSE
    # Acquire the lock for the thread to prevent data from overlapping.
    dataLock.acquire()
    if VERBOSE>=2:
        print(data)

    # Write the new levels to each zone.
    for zone in range(QSE_ZONES):
        zoneValues[zone] = data[DMX_START_ADDRESS+zone]

    # Keep up to date with the last update to determine rather or not to unlock mqtt support.
    lastDMXUniverseUpdate = time.time()

    # Allow the next command call to follow through by releasing the lock.
    dataLock.release()

# This function is a thread that writes any changes to the QSE controller.
def qse_write_zone_values():
    global sendAllDataThisTImeLock, dataLock, sendAllDataThisTime, zoneValues, sentValues, QSE_ZONES
    while True:

        # If control is disabled, we won't check this time.
        if controlDisabled:
            # Prevent CPU overload and wait half a second before continuing.
            time.sleep(0.5)
            continue


        # Acquire lock to prevent conflict between threads.
        dataLock.acquire()

        # Copy zone values locally to allow changes by other threads while we send.
        thisZoneValues = zoneValues.copy()

        # Allow the next command call to follow through by releasing the lock.
        dataLock.release()

        # Acquire send all data this time lock.
        sendAllDataThisTImeLock.acquire()

        # Check for changes in zones values and send it.
        for zone in range(QSE_ZONES):
            # If zone value is the same and we're not sending all zone data this time, skip sending.
            if thisZoneValues[zone]==sentValues[zone] and not sendAllDataThisTime:
                continue

            # Update the array of sent values.
            sentValues[zone] = thisZoneValues[zone]
            
            # Send value via QSE NWK
            qse_send_zone_value(zone+1, thisZoneValues[zone])

        # Reset the flag of send all data to false as we would have sent all data this time.
        sendAllDataThisTime = False

        # Release the lock.
        sendAllDataThisTImeLock.release()

        # Lower CPU usage.
        time.sleep(0.1)


# This function reads the serial data from the QSE NWK line by line and performs a few functions based on response.
def qse_read():
    global serialSession, controlDisabled, sendAllDataThisTime, mqttLightBrightness, mqttLightState, VERBOSE
    # Creates a bufferred reader for the serial input.
    sio = io.TextIOWrapper(io.BufferedReader(serialSession))

    # We want to run this forever as we are in a thread.
    while True:
        # Gets the next available line from the QSE NWK and filter out the QSE prompt and any new line characters.
        line = sio.readline().replace("QSE>","").rstrip()
        if line=="":
            continue

        # If the command not found error is returned, this is either due to
        #  the Lutron GRAFIK Eye QS Control panel not being assigned an integration ID of 1,
        #  or due to a bug which needs the QSE NWK rebooted to fix. We attempt to reboot
        #  to attempt to automatically fix the bug.
        if line=="~ERROR,6":
            if VERBOSE>=2:
                print("Error occurred, rebooting QSE NWK.")
            # Send the reboot command.
            serialSession.write(bytes("#RESET,0\n\r", 'utf-8'))

        # If the all zone up button is pressed, we disable control from the program to allow someone to manually control zones.
        elif line=="~DEVICE,1,74,3":
            if VERBOSE>=2:
                print("Received disable signal.")
            controlDisabled = True

        # If the all zone down button is pressed, we re-enable the programs control of the zones.
        elif line=="~DEVICE,1,75,3":
            if VERBOSE>=2:
                print("Received enable signal.")
            controlDisabled = False
            sendAllDataThisTime = True

        # If none of the above, and is a device notification, we parse.
        elif line.startswith("~DEVICE,1"):
            data = line.split(",")
            # If brightness notice and zone 1, let's update MQTT.
            if data[3]=="14" and data[2]=="1":
                # Acquire lock to prevent conflict between threads.
                dataLock.acquire()

                # Convert brightness to MQTT light state.
                mqttLightBrightness = round((float(data[4])/100.00)*255,0)
                if mqttLightBrightness==0:
                    # If control was disabled, and brightness is now 0, disable the control disablement.
                    if controlDisabled:
                        controlDisabled = False
                    mqttLightState = MQTT_LIGHT_OFF
                else:
                    mqttLightState = MQTT_LIGHT_ON
                
                # Publish current state to MQTT.
                mqtt_publish_state()

                # Allow the next command call to follow through by releasing the lock.
                dataLock.release()

        if VERBOSE>=1:
            print(line)

# Reset the send all data flag every 10 seconds to ensure all zones have the correct value set.
def qse_reset_sendAllDataThisTime():
    global sendAllDataThisTImeLock, sendAllDataThisTime, VERBOSE
    while True:
        # Wait 10 seconds before running.
        time.sleep(10)

        # Acquire send all data this time lock.
        sendAllDataThisTImeLock.acquire()

        # Reset
        if VERBOSE>=3:
            print("Resetting flag to send all data")
        sendAllDataThisTime = True

        # Release the lock.
        sendAllDataThisTImeLock.release()

# Sends the current MQTT light state to MQTT.
def mqtt_publish_state():
    global mqtt_conn, mqttLightState, mqttLightBrightness, mqttSentLightState, mqttSentLightBrightness, VERBOSE
    # If we already sent this message, no duplicates.
    if mqttLightState==mqttSentLightState and mqttLightBrightness==mqttSentLightBrightness:
        return
    mqttSentLightState = mqttLightState
    mqttSentLightBrightness = mqttLightBrightness

    # Generate json format of current state.
    msg = json.dumps({"brightness": mqttLightBrightness,"state": mqttLightState})
    # Send message.
    result = mqtt_conn.publish(MQTT_TOPIC, msg)
    # result: [0, 1]
    status = result[0]
    if status == 0 and VERBOSE>=2:
        print(f"Send `{msg}` to topic `{MQTT_TOPIC}`")
    if status != 0:
        print(f"Failed to send message to topic {MQTT_TOPIC}")

# Receives MQTT messages from subscribed topics.
def mqtt_on_message(client, userdata, msg):
    global mqttLightState, mqttLightBrightness, mqttSentLightState, mqttSentLightBrightness, lastDMXUniverseUpdate, VERBOSE
    # If message received is to the JSON set topic, update light state.
    if msg.topic==MQTT_TOPIC_SET:
        # Decode JSON from the message.
        decoded_message=str(msg.payload.decode("utf-8"))
        data = json.loads(decoded_message)
        if VERBOSE>=2:
            print(f"Received `{data}` from `{msg.topic}` topic")

        # Acquire lock to prevent conflict between threads.
        dataLock.acquire()
        
        # Check message for brightness and state values/update accordingly.
        if "brightness" in data:
            mqttLightBrightness = data["brightness"]
        if "state" in data:
            if mqttLightState!=data["state"]:
                mqttLightState = data["state"]
                # If light state is on, but brightness value is off, set brightness to 50%.
                if mqttLightState==MQTT_LIGHT_ON and mqttLightBrightness==0:
                    mqttLightBrightness = 127
        
        # Check to see if it has been more than 5 seconds since the last DMX universe update, if it has been, we're allowed to control the lights.
        durationSinceLastDMXUniverseUpdate = time.time() - lastDMXUniverseUpdate
        if durationSinceLastDMXUniverseUpdate>5:
            # If state is on, set brightness levels to all zones.
            if mqttLightState==MQTT_LIGHT_ON:
                for zone in range(QSE_ZONES):
                    zoneValues[zone] = mqttLightBrightness
            else: # If state is off, set brightness level of 0.
                for zone in range(QSE_ZONES):
                    zoneValues[zone] = 0
        else:
            # If locked due to DMX control, force values to first zone value.
            mqttLightBrightness = zoneValues[0]
            if mqttLightBrightness==0:
                mqttLightState = MQTT_LIGHT_OFF
            else:
                mqttLightState = MQTT_LIGHT_ON

            mqttSentLightState = ""
            mqttSentLightBrightness = 0

        # Publish current state to MQTT.
        mqtt_publish_state()

        # Allow the next command call to follow through by releasing the lock.
        dataLock.release()
    elif msg.topic!=MQTT_TOPIC:
        print(f"Received unknown message `{msg.payload.decode()}` from `{msg.topic}` topic")

# Subscribes to the MQTT topic for this light.
def mqtt_subscribe():
    global mqtt_conn
    mqtt_conn.subscribe(MQTT_TOPIC+"/#")

# When the MQTT broker is connected, this function is called.
def mqtt_on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT Broker!")
        # New connection means we must publish state and subscribe to our topic.
        mqtt_subscribe()
        mqtt_publish_state()
    else:
        print("Failed to connect, return code %d\n", rc)

# The MQTT thread for connection to the MQTT broker.
def mqtt_connect():
    global mqtt_conn
    try:
        mqtt_conn = mqtt_client.Client(MQTT_CLIENT_ID)
        if MQTT_USERNAME!="":
            mqtt_conn.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        mqtt_conn.on_connect = mqtt_on_connect
        mqtt_conn.on_message = mqtt_on_message
        mqtt_conn.connect(MQTT_BROKER, MQTT_PORT)
        mqtt_conn.loop_forever()
    except:
        print("MQTT Connection Failed, trying again in 10 seconds.\n")
        time.sleep(10.0)
        mqtt_connect()

# Build array with 0% in each zone.
for zone in range(QSE_ZONES):
    zoneValues.append(0)
    sentValues.append(0)

# Connect to the QSE NWK by using the serial port.
print("Connecting to QSE NWK at: "+QSE_NWK_DEVICE)
with serial.Serial(QSE_NWK_DEVICE, QSE_NWK_BAUD, timeout=2) as ser:
    serialSession = ser

# If the serial session is still set to None, we did not correctly connect.
if serialSession == None:
    print("Failed to connect.")
    exit(1)

# We connected, so we can open the device.
serialSession.open()

# Now that we are ready to roll, we start the read thread.
_thread.start_new_thread(qse_read, ())

# Start the write thread.
_thread.start_new_thread(qse_write_zone_values, ())

# Start the reset send all data thread.
_thread.start_new_thread(qse_reset_sendAllDataThisTime, ())

# Start the MQTT light thread.
if MQTT_ENABLED:
    _thread.start_new_thread(mqtt_connect, ())

# Connect to the DMX universe with the OLA wrapper.
wrapper = ClientWrapper()
client = wrapper.Client()
client.RegisterUniverse(DMX_UNIVERSE, client.REGISTER, dmx_universe_update)
wrapper.Run()
