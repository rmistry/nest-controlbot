#Nest ControlBot

**A library that gives fine-grained control over the Nest Thermostat and uses a remote sensor.**

##Background

The motivation behind the creation of this library is detailed here:
http://mistrybytes.blogspot.com/2015/02/nest-controlbot.html

##Hardware Prerequisites

* [Raspberry Pi](http://www.raspberrypi.org/).
* DS18B20 digital temperature sensor. I prefer the [long movable version](http://www.amazon.com/Vktech-DS18b20-Waterproof-Temperature-Transmitter/dp/B00CHEZ250/).

Assemble both using these [instructions](https://learn.adafruit.com/downloads/pdf/adafruits-raspberry-pi-lesson-11-ds18b20-temperature-sensing.pdf).

##Algorithm

The controlbot runs continuously and checks a specified JSON schedules file. If the current time
falls in the range specified in the schedules file, then it starts communicating with Nest to
achieve the desired room temperature. The code also accounts for intermittent lapses in internet
connections by retrying requests.

Uses the following high-level algorithm:
```
if root_temperature is less than the (target_temperature - specified_range):
  set Nest to one degree more than Nest's ambient temperature so that it turns on.
else:
  set Nest to one degree less than Nest's ambient temperature so that it does not turn on.
```
*The implementation talks to the Nest API by using a controlbot modified version of pynest by Scott M Baker, smbaker@gmail.com, http://www.smbaker.com/*

##Usage

* Create .nest_username, .nest_password, .serial hidden files in the root checkout directory.
* Populate schedule.json using the current file as an example.
* Create .webapp_password to integrate with your instance of [nest-controlbot-webapp](https://github.com/rmistry/nest-controlbot-webapp).
* Run `python nest_controlbot.py`

##Limitations

* Does not handle overlapping schedules. The first schedule it sees in the range is the one it uses.
* Does not work with multiple temperature sensors. This would be simple to fix if needed.

---
