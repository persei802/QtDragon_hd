#!/usr/bin/python3
#    This is a userspace program that interfaces Huanyang GT-series VFDs
#    to the LinuxCNC HAL.

#    Copyright (C) 2022 Jim Sloot <persei802@gmail.com>
#    Created from the original hy_gt_vfd.c by Sebastian Kuzminsky
#    This program is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation, version 2.

#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    General Public License for more details.

#    You should have received a copy of the GNU Lesser General Public
#    License along with this program; if not, write to the Free Software
#    Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301-1307 USA.

import sys
import hal, time
import argparse
from qtvcp import logger
from pymodbus.client import ModbusSerialClient

LOG = logger.getLogger(__name__)
LOG.setLevel(logger.INFO)

# state machine states
INIT = 1
RUNNING = 2
ERROR = 3

# Any options not specified in the command line will use the default values listed below.
device = "/dev/ttyUSB0"
byte_size = 8
baud_rate = 38400
parity = "N"
stop_bits = 1
slave = 1
max_speed = 24000
min_speed = 7200
last_speed = 0
period = 0.25 # seconds to sleep before each cycle
retries = 3
motor_is_on = False
baud_values = ["1200", "2400", "4800", "9600", "19200", "38400"]
parity_values = ["E", "O", "N"]
stop_values = ["1", "2"]
byte_values = ["5", "6", "7", "8"]

h = hal.component("hy_gt_vfd")
parser = argparse.ArgumentParser()

# Parse command line options
def parse_args():
    global device, baud_rate, parity, stop_bits, byte_size, slave, max_speed, min_speed
    parser.add_argument("-d", "--device", help="serial device")
    parser.add_argument("-b", "--bits", help="number of bits")
    parser.add_argument("-r", "--rate", help="baudrate")
    parser.add_argument("-p", "--parity", help="parity")
    parser.add_argument("-s", "--stopbits", help="stop bits")
    parser.add_argument("-t", "--slave", help="modbus slave number")
    parser.add_argument("-M", "--maxrpm", help="max motor speed in RPM")
    parser.add_argument("-m", "--minrpm", help="min motor speed in RPM")
    args = parser.parse_args()
    if args.device:
        device = args.device
    if args.bits:
        if args.bits in byte_values:
            byte_size = int(args.bits)
        else:
            print("Invalid byte size - using default of {}".format(byte_size))
            print("Must be one of ", byte_values)
    if args.rate:
        if args.rate in baud_values:
            baud_rate = int(args.rate)
        else:
            print("Invalid baud rate - using default of {}".format(baud_rate))
            print("Must be one of ", baud_values)
    if args.parity:
        if args.parity in parity_values:
            parity = args.parity
        else:
            print("Invalid parity setting - using default of {}".format(parity))
            print("Must be one of ", parity_values)
    if args.stopbits:
        if args.stopbits in stop_values:
            stop_bits = int(args.stopbits)
        else:
            print("Invalid stop bits - using default of {}".format(stop_bits))
            print("Must be one of ", stop_values)
    if args.slave:
        if 1 <= int(args.slave) <= 127:
            slave = int(args.slave)
        else:
            print("Slave address must be between 1 and 127")
    if args.maxrpm:
        if float(args.maxrpm) == 0:
            print('FATAL ERROR - Max RPM = 0')
            raise SystemExit
        elif float(args.maxrpm) > min_speed:
            max_speed = float(args.maxrpm)
        else:
            print("Max RPM must be greater than Min RPM")
    if args.minrpm:
        if float(args.minrpm) < max_speed:
            min_speed = float(args.minrpm)
        else:
            print("Min RPM must be less than Max RPM")

# Initialize the serial port
def init_serial():
    global vfd
    params = {'port': device,
              'baudrate': baud_rate,
              'parity': parity,
              'stopbits': stop_bits,
              'bytesize': byte_size,
              'timeout': 1}
    vfd = ModbusSerialClient(method='rtu', **params)
    if vfd.connect(): return True
    return False
 
# Create HAL pins
def init_pins():
    h.newpin('speed-cmd', hal.HAL_FLOAT, hal.HAL_IN)
    h.newpin('speed-fb', hal.HAL_FLOAT, hal.HAL_OUT)
    h.newpin('spindle-on', hal.HAL_BIT, hal.HAL_IN)
    h.newpin('spindle-inhibit', hal.HAL_BIT, hal.HAL_IN)
    h.newpin('reverse', hal.HAL_BIT, hal.HAL_IN)
    h.newpin('at-speed', hal.HAL_BIT, hal.HAL_OUT)
    h.newpin('output-current', hal.HAL_FLOAT, hal.HAL_OUT)
    h.newpin('output-voltage', hal.HAL_FLOAT, hal.HAL_OUT)
    h.newpin('fault-info-code', hal.HAL_U32, hal.HAL_OUT)
    h.newpin('modbus-errors', hal.HAL_U32, hal.HAL_OUT)
    h['modbus-errors'] = 0
    h.ready()

def set_motor_on():
    global motor_is_on, retries
    if motor_is_on is False:
        motor_is_on = True
        error = True
        direction = 2 if h['reverse'] else 1
        for i in range(retries):
            time.sleep(delay)
            req = vfd.write_register(0x1000, direction, slave = slave)
            if not req.isError():
                error = False
                break
        if error is True:
            print("Motor On: Error writing to register 0x1000")

def set_motor_off():
    global motor_is_on, retries
    if motor_is_on is True:
        motor_is_on = False
        h['at-speed'] = False
        error = True
        for i in range(retries):
            time.sleep(delay)
            req = vfd.write_register(0x1000, 5, slave = slave)
            if not req.isError():
                error = False
                break
        if error is True:
            print("Motor Off: Error writing to register 0x1000")

# Set spindle speed as percentage of maximum speed
def set_motor_speed():
    global last_speed, retries
    speed = h['speed-cmd']
    if speed == last_speed: return
    last_speed = speed
    if speed > max_speed:
        speed_cmd = 10000
    elif speed < min_speed:
        speed_cmd = int((min_speed / max_speed) * 10000)
    else:
        speed_cmd = int((speed / max_speed) * 10000)
    error = True
    for i in range(retries):
        time.sleep(delay)
        req = vfd.write_register(0x2000, speed_cmd, slave = slave)
        if not req.isError():
            error = False
            break
    if error is True:
        print("Error writing to register 0x2000")

def read_mb_register(addr):
    global currentState, retries
    rtn_data = None
    # Try is in case of USB port disconnection. The state machine will go to ERROR state
    # and then to INIT where it will remain until the connection is re-established.
    try:
        for i in range(retries):
            time.sleep(delay)
            data = vfd.read_holding_registers(address = addr, count = 1, slave = slave)
            if not data.isError():
                rtn_data = data.registers[0]
                break
        if rtn_data is None:
            h['modbus-errors'] += 1
            print(f"Error reading register {hex(addr)}")
    except Exception as e:
        print(f"Exception - {e}")
        currentState = ERROR
    return rtn_data

def get_vfd_data():
    data = read_mb_register(0x3003)
    if data is not None:
        h['output-voltage'] = data
    data = read_mb_register(0x3004)
    if data is not None:
        h['output-current'] = data
    data = read_mb_register(0x3005)
    if data is not None:
        h['speed-fb'] = data
    data = read_mb_register(0x5000)
    if data is not None:
        h['fault-info-code'] = data

def set_atspeed():
    speed_cmd = h['speed-cmd']
    speed_fb = h['speed-fb']
    if speed_cmd == 0: 
        h['at-speed'] = False
    elif abs((speed_cmd - speed_fb) / speed_cmd) <= 0.02:
        h['at-speed'] = True
    else:
        h['at-speed'] = False

## start
currentState = INIT
prevState = None
delay = 80 / baud_rate
parse_args()
init_pins()

try:
    while True:
        time.sleep(period)
        if currentState == INIT:
            if currentState != prevState:
                LOG.info("State : VFD INIT")
                prevState = currentState
            if init_serial():
                LOG.info(f"Connected to {device}")
                LOG.debug(f"VFD object : {vfd}")
                currentState = RUNNING
            else:
                LOG.debug(f"Could not connect to {device}")
                time.sleep(1)

        elif currentState == RUNNING:
            if currentState != prevState:
                LOG.info("State : VFD RUNNING")
                prevState = currentState
            get_vfd_data()
            if h['spindle-inhibit'] is True:
                set_motor_off()
            elif h['spindle-on'] is True:
                set_motor_on()
                set_motor_speed()
                set_atspeed()
            else:
                set_motor_off()

        elif currentState == ERROR:
            LOG.info("State : VFD ERROR")
            del vfd
            prevState = currentState
            currentState = INIT

except KeyboardInterrupt:
    raise SystemExit

