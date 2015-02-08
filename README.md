#nest_autobot

**A library that gives fine grain control over the Nest Thermostat**
 
##Usage

### Module

You can import the module as `nest_thermostat`. Use the source, luke!

Tips: you need to manually call `.login()` first, and `.get_status()` before `.show_*()`

### Command line
```
syntax: nest.py [options] command [command_args]
options:
   --user <username>      ... username on nest.com
   --password <password>  ... password on nest.com
   --celsius              ... use celsius (the default is farenheit)
   --serial <number>      ... optional, specify serial number of nest to use
   --index <number>       ... optional, 0-based index of nest
                                (use --serial or --index, but not both)

commands:
    temp <temperature>         ... set target temperature
    fan [auto|on]              ... set fan state
    mode [cool|heat|range|off] ... set fan state
    away                       ... toggle away
    show                       ... show everything
    curtemp                    ... print current temperature
    curhumid                   ... print current humidity
    curmode                    ... print current mode
    curtarget                  ... print current target temp

examples:
    nest.py --user joe@user.com --password swordfish temp 73
    nest.py --user joe@user.com --password swordfish fan auto
```

*fork of pynest by Scott M Baker, smbaker@gmail.com, http://www.smbaker.com/*

---
