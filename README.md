SPD EEPROM Tool
===============

A simple command line tool for reading and writing AT24/EE1004 SPD EEPROMs.

AUR: [spd-eeprom](https://aur.archlinux.org/packages/spd-eeprom)

## Dependencies

```
python
```

## Usage

* DIMM: DIMM slot index (0 - 7)
* FILE: input or output file path

### Read data from SPD EEPROM

```
sudo spd-eeprom.py -r -d DIMM -f FILE
```

### Write data to SPD EEPROM

```
sudo spd-eeprom.py -w -d DIMM -f FILE
```
