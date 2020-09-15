#!/usr/bin/env python3
#
# spd-eeprom.py  --  A simple command line tool for reading and writing AT24/EE1004 SPD EEPROMs.
#
# Copyright 2020 Jack Chen <redchenjs@live.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys
import time
import ctypes
import getopt
import subprocess

try:
    import fcntl
except ImportError:
    print("This operating system is not supported.")
    exit(1)

# To determine what functionality is present
I2C_FUNC_I2C = 0x00000001

# Data for SMBus Messages
class i2c_smbus_data(ctypes.Union):
    _fields_ = [
        ("byte", ctypes.c_uint8)
    ]

# SMBus read or write markers
I2C_SMBUS_READ  = 1
I2C_SMBUS_WRITE = 0

# SMBus transaction types
I2C_SMBUS_QUICK     = 0
I2C_SMBUS_BYTE      = 1
I2C_SMBUS_BYTE_DATA = 2

# "/dev/i2c-X" ioctl commands
I2C_SLAVE = 0x0703  # Use this slave address
I2C_FUNCS = 0x0705  # Get the adapter functionality mask
I2C_SMBUS = 0x0720  # SMBus transfer

# This is the structure as used in the I2C_SMBUS ioctl call
class i2c_smbus_ioctl_data(ctypes.Structure):
    _fields_ = [
        ("read_write", ctypes.c_uint8),
        ("command", ctypes.c_uint8),
        ("size", ctypes.c_uint32),
        ("data", ctypes.POINTER(i2c_smbus_data))
    ]
    @staticmethod
    def create(read_write, command, size):
        data = i2c_smbus_data()
        return i2c_smbus_ioctl_data(read_write=read_write, command=command, size=size,
                                    data=ctypes.POINTER(i2c_smbus_data)(data))

def i2c_smbus_get_funcs(fd):
    funcs = ctypes.c_uint32()
    fcntl.ioctl(fd, I2C_FUNCS, funcs)
    return funcs.value

def i2c_smbus_read_byte(fd, addr):
    fcntl.ioctl(fd, I2C_SLAVE, addr)
    msg = i2c_smbus_ioctl_data.create(read_write=I2C_SMBUS_READ, command=0, size=I2C_SMBUS_BYTE)
    fcntl.ioctl(fd, I2C_SMBUS, msg)
    return msg.data.contents.byte

def i2c_smbus_read_byte_data(fd, addr, reg):
    fcntl.ioctl(fd, I2C_SLAVE, addr)
    msg = i2c_smbus_ioctl_data.create(read_write=I2C_SMBUS_READ, command=reg, size=I2C_SMBUS_BYTE_DATA)
    fcntl.ioctl(fd, I2C_SMBUS, msg)
    return msg.data.contents.byte

def i2c_smbus_write_quick(fd, addr):
    fcntl.ioctl(fd, I2C_SLAVE, addr)
    msg = i2c_smbus_ioctl_data.create(read_write=I2C_SMBUS_WRITE, command=0, size=I2C_SMBUS_QUICK)
    fcntl.ioctl(fd, I2C_SMBUS, msg)

def i2c_smbus_write_byte_data(fd, addr, reg, val):
    fcntl.ioctl(fd, I2C_SLAVE, addr)
    msg = i2c_smbus_ioctl_data.create(read_write=I2C_SMBUS_WRITE, command=reg, size=I2C_SMBUS_BYTE_DATA)
    msg.data.contents.byte = val
    fcntl.ioctl(fd, I2C_SMBUS, msg)

def print_usage():
    print("Usage:")
    print("   ", sys.argv[0], "-l")
    print("   ", sys.argv[0], "-r -d DIMM -f FILE")
    print("   ", sys.argv[0], "-w -d DIMM -f FILE")
    print()
    print("Options:")
    print("    -l           list used DIMM slots")
    print("    -r           read data from SPD EEPROM (output to file)")
    print("    -w           write data to SPD EEPROM (input from file)")
    print("    -d DIMM      DIMM slot index (0 - 7)")
    print("    -f FILE      input or output file path")

def spd_set_page(fd, page):
    try:
        i2c_smbus_write_quick(fd, 0x36 + page)
    except IOError:
        return False

    return True

def spd_read(fd, smbus_idx, dimm_slot, file_path):
    real_path = os.path.realpath(file_path)
    if not os.access(os.path.dirname(real_path), os.W_OK) or os.path.isdir(real_path):
        print("Could not write file:", file_path)
        sys.exit(1)

    ee1004 = spd_set_page(fd, 0)

    print("Reading from %s SPD EEPROM: 0x5%d on SMBus %d" % ("EE1004" if ee1004 else "AT24", dimm_slot, smbus_idx))

    spd_file = open(file_path, "wb")

    for page in range(0, 2):
        print()

        if ee1004:
            if spd_set_page(fd, page):
                print("SPD PAGE %d:" % page)
            else:
                print("Set SPD PAGE %d failed." % page)
                sys.exit(1)

        for index in range(0, 256):
            print("Reading at 0x%02x" % index, end="\r")

            try:
                res = i2c_smbus_read_byte_data(fd, 0x50 + dimm_slot, index)
            except IOError:
                print("\n\nRead failed.")
                sys.exit(1)

            spd_file.write(res.to_bytes(1, byteorder="little"))

        print()

        if not ee1004:
            break

    print("\nRead done.")

def spd_write(fd, smbus_idx, dimm_slot, file_path):
    real_path = os.path.realpath(file_path)
    if not os.access(real_path, os.R_OK) or os.path.isdir(real_path):
        print("Could not read file:", file_path)
        sys.exit(1)

    ee1004 = spd_set_page(fd, 0)

    file_size = os.path.getsize(file_path)
    if not ee1004 and file_size != 256:
        print("The SPD file must be exactly 256 bytes!")
        sys.exit(1)
    elif ee1004 and file_size != 512:
        print("The SPD file must be exactly 512 bytes!")
        sys.exit(1)

    print("Writing to %s SPD EEPROM: 0x5%d on SMBus %d" % ("EE1004" if ee1004 else "AT24", dimm_slot, smbus_idx))

    print("\nWARNING! Writing wrong data to SPD EEPROM will leave your system UNBOOTABLE!")
    ans = input("Continue anyway? [y/N] ").lower()
    if ans != "y":
        print("\nWrite aborted.")
        sys.exit(1)

    spd_file = open(file_path, "rb")

    for page in range(0, 2):
        print()

        if ee1004:
            if spd_set_page(fd, page):
                print("SPD PAGE %d:" % page)
            else:
                print("Set SPD PAGE %d failed." % page)
                sys.exit(1)

        for index in range(0, 256):
            byte = int.from_bytes(spd_file.read(1), byteorder="little")

            print("Writing at 0x%02x (0x%02x)" % (index, byte), end="\r")

            try:
                i2c_smbus_write_byte_data(fd, 0x50 + dimm_slot, index, byte)
            except IOError:
                print("\n\nWrite failed.")
                sys.exit(1)

            time.sleep(0.01)    # necessary delay when writing data to SPD EEPROM

        print()

        if not ee1004:
            break

    print("\nWrite done.")

def smbus_probe(dimm_slot = None):
    try:
        args = ["rmmod", "at24", "ee1004", "eeprom"]
        proc = subprocess.Popen(args=args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.communicate()

        args = ["modprobe", "i2c_dev"]
        proc = subprocess.Popen(args=args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.communicate()
    except Exception:
        pass

    smbus_idx = ""

    files = os.listdir("/dev")
    files = list(filter(lambda x: x.startswith("i2c-"), files))

    for entry in files:
        fd = os.open("/dev/" + entry, os.O_RDWR)
        if not i2c_smbus_get_funcs(fd) & I2C_FUNC_I2C:
            smbus_idx = entry[4:]
            break

    if smbus_idx.isdigit():
        smbus_idx = int(smbus_idx)
    else:
        print("No SMBus adapter found.")
        sys.exit(1)

    if dimm_slot == None:
        print("Probing for SPD EEPROM on SMBus %d" % smbus_idx)
        print()

        eeprom = 0
        ee1004 = spd_set_page(fd, 0)

        for slot in range(0, 8):
            try:
                i2c_smbus_read_byte(fd, 0x50 + slot)

                print("DIMM slot %d: %s SPD EEPROM" % (slot, "512 Byte EE1004" if ee1004 else "256 Byte AT24"))

                eeprom += 1
            except IOError:
                pass

        if eeprom == 0:
            print("No SPD EEPROM detected.")
    else:
        try:
            i2c_smbus_read_byte(fd, 0x50 + dimm_slot)
        except IOError:
            print("DIMM slot %d is empty." % dimm_slot)
            sys.exit(1)

        return fd, smbus_idx

def main():
    if os.getuid():
        print("Please run this script as root.")
        sys.exit(1)

    try:
        opts, _args = getopt.getopt(sys.argv[1:], "lrwd:f:")
    except getopt.error:
        print_usage()
        sys.exit(1)

    op_code = 0
    dimm_slot = ""
    file_path = ""

    for opt, arg in opts:
        if opt in ("-l"):
            op_code = 1
        elif opt in ("-r"):
            op_code = 2
        elif opt in ("-w"):
            op_code = 3
        elif opt in ("-d"):
            dimm_slot = arg
        elif opt in ("-f"):
            file_path = arg

    if op_code == 1 and len(opts) == 1:
        smbus_probe()
    elif op_code != 0 \
        and len(opts) == 3 \
        and len(file_path) != 0 \
        and dimm_slot.isdigit() \
        and 0 <= int(dimm_slot) <= 7:

        fd, smbus_idx = smbus_probe(int(dimm_slot))

        if op_code == 2:
            spd_read(fd, smbus_idx, int(dimm_slot), file_path)
        elif op_code == 3:
            spd_write(fd, smbus_idx, int(dimm_slot), file_path)
    else:
        print_usage()
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        exit(1)
