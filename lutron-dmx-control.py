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

# Documentation
# This program is designed to use the Open Lighting Arcretechture (OLA) to receive a DMX signal
#  and translate to commands to control the 6 dimiable zones on the Lutron GRAFIK Eye QS Control panel
#  through the use of a QSE-CI-NWK-E. This program uses the serial port for reliability.

# Configuration
# Serial port device to use to communicate with Lutron's QSE NWK.
QSE_NWK_DEVICE = "/dev/ttyUSB0"
# Set baud rate on Lutron's QSE NWK.
QSE_NWK_BAUD = 115200
# DMX Universe in OLA that is used.
DMX_UNIVERSE = 3
# The starting address.
DMX_START_ADDRESS = 0

#Verbosity
VERBOSE=1

# Variables used at run time, do not adjust.
serialSession = None
currentValues = [0,0,0,0,0,0]
sendAllDataThisTime = True
controlDisabled = False

# To prevent data from overlapping which is known to crash the QSE NWK, we implement a thread lock which must be released before being obtained.
dataLock = threading.Lock()

# This fucnction translates the 0-255 signal from DMX to 0.00 to 100.00 signal used by Lutron,
#  and it sends the appropiate command to the QSE NWK to change the brightness level of a zone.
def SetZone(zone, value):
    global serialSession, currentValues, sendAllDataThisTime, controlDisabled
    # We only want to translate a level of it has not already been sent to the zone,
    #  or if we want to send all data this time. However we do not want to send the level
    #  if the controls has been disabled by the designated button on the control panel.
    if (currentValues[zone-1]==value and not sendAllDataThisTime) or controlDisabled:
        return

    # Update the array of current values.
    currentValues[zone-1] = value

    # Translate to the command.
    command = "#DEVICE,1,%d,14,%.2f,00:00" % (zone,round((value/255.00)*100,2))
    if VERBOSE>=1:
        print(command)

    # Send to the QSE NWK.
    serialSession.write(bytes(command+"\n\r", 'utf-8'))

def NewData(data):
    global sendAllDataThisTime, dataLock
    # Acquire the lock for the thread to prevent data from overlapping.
    dataLock.acquire()
    if VERBOSE>=2:
        print(data)

    # Send the new levels to each zone via the QSE NWK.
    SetZone(1,data[DMX_START_ADDRESS+0])
    SetZone(2,data[DMX_START_ADDRESS+1])
    SetZone(3,data[DMX_START_ADDRESS+2])
    SetZone(4,data[DMX_START_ADDRESS+3])
    SetZone(5,data[DMX_START_ADDRESS+4])
    SetZone(6,data[DMX_START_ADDRESS+5])

    # Reset the flag of send all data to false as we would have sent all data this time.
    sendAllDataThisTime = False

    # Allow the next command call to follow through by releasing the lock.
    dataLock.release()

# This function reads the serial data from the QSE NWK line by line and performs a few functions based on response.
def QSE_Read():
    global serialSession, controlDisabled
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
        if line=="~DEVICE,1,74,3":
            if VERBOSE>=2:
                print("Received disable signal.")
            controlDisabled = True

        # If the all zone down button is pressed, we re-enable the programs control of the zones.
        if line=="~DEVICE,1,75,3":
            if VERBOSE>=2:
                print("Received enable signal.")
            controlDisabled = False
            sendAllDataThisTime = True

        if VERBOSE>=1:
            print(line)

# Reset the send all data flag every 10 seconds to ensure all zones have the correct value set.
def sendAllDataReset():
    global sendAllDataThisTime
    while True:
        time.sleep(10)
        if VERBOSE>=3:
            print("Resetting flag to send all data")
        sendAllDataThisTime = True

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
_thread.start_new_thread(QSE_Read, ())

# Start the reset send all data thread.
_thread.start_new_thread(sendAllDataReset, ())

# Connect to the DMX universe with the OLA wrapper.
wrapper = ClientWrapper()
client = wrapper.Client()
client.RegisterUniverse(DMX_UNIVERSE, client.REGISTER, NewData)
wrapper.Run()
