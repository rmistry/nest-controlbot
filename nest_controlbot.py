#! /usr/bin/python

"""Bot that adjusts the Nest thermostat using a JSON schedule.

This is currently only setup for heat since it was winter when I wrote it.
"""


import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import pytz
import time
import urllib
import urllib2

# Below is from https://github.com/timofurrer/w1thermsensor
from w1thermsensor import W1ThermSensor

import nest
from nest import utils as nest_utils


# Nest account constants.
LOGIN_FILE = '.nest_username'
PASSWORD_FILE = '.nest_password'
SERIAL_FILE = '.serial'
WEBAPP_PASSWORD_FILE = '.webapp_password'

LOCATION_TZ = pytz.timezone('US/Eastern')
# LOCATION_TZ = pytz.timezone('America/New_York')
SCHEDULES_FILE = 'schedules.json'
POLLING_FREQUENCY_SECS = 5*60  # 5 mins
WEBAPP_URL = 'https://mistry-nest-controlbot.appspot.com/'

# Create logger
logger = logging.getLogger('nest_controlbot')
logger.setLevel(logging.INFO)

handler = RotatingFileHandler('nest_controlbot.log', maxBytes=10*1024,
                              backupCount=5)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s %(levelname)s:%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


class retry(object):
  """Decorator that retires a function 120 times after sleeping for a min."""
  def __call__(self, f):
    def fn(*args, **kwargs):
      exception = None
      for _ in range(120):
        try:
          return f(*args, **kwargs)
        except Exception, e:
          print "Retrying after sleeping for 60s due to: " + str(e)
          time.sleep(60)
          exception = e
      #if no success after tries, raise last exception
      raise exception
    return fn


def _read_file(filepath):
  """Read from the specified file."""
  if os.path.exists(filepath) and os.path.isfile(filepath):
    return open(filepath, 'r').read().rstrip()


def _get_credentials():
  """Returns the login and password to use when connecting to nest."""
  login = _read_file(LOGIN_FILE)
  password = _read_file(PASSWORD_FILE)
  if not login or not password:
    raise Exception('Must create %s and %s' % (LOGIN_FILE, PASSWORD_FILE))
  return login, password


def _get_webapp_password():
  """Returns the password to use when talking to the webapp."""
  password = _read_file(WEBAPP_PASSWORD_FILE)
  if not password:
    raise Exception('Must create %s' % WEBAPP_PASSWORD_FILE)
  return password


def _get_serial():
  """Returns the serial of the nest thermostat."""
  return _read_file(SERIAL_FILE)


def _get_schedules():
  """Returns list of schedules from the schedules JSON."""
  json_data = open(SCHEDULES_FILE)
  data = json.load(json_data)
  json_data.close()

  schedules = []
  for json_schedule in data['schedules']:
    schedule = Schedule(
        start_time=json_schedule['start-time'],
        end_time=json_schedule['end-time'],
        target_temp=json_schedule['target-temp'],
        target_temp_range=json_schedule['target-temp-range'],
        heat=json_schedule['heat'],
        managed_by_nest=json_schedule['managed-by-nest'],
        added_by=json_schedule['added-by'],
    )
    schedules.append(schedule)
  return schedules


class Schedule:
  """Container for the different schedule parameters."""
  def __init__(self, start_time, end_time, target_temp, target_temp_range,
               heat, managed_by_nest, added_by):
    self.start_time = start_time
    self.end_time = end_time
    self.target_temp = float(target_temp)
    self.target_temp_range = float(target_temp_range)
    self.heat = heat == "True"
    self.managed_by_nest = managed_by_nest == "True"
    self.added_by = added_by


def _getCurrentTime():
  """Returns the current time in HH:MM."""
  return LOCATION_TZ.localize(datetime.datetime.now()).strftime("%H:%M")


def _getRoomTemperature():
  """Returns the room temperature as reported from Raspberry Pi."""
  sensor = W1ThermSensor()
  roomTemp = sensor.get_temperature(W1ThermSensor.DEGREES_F)
  return float("{0:.2f}".format(roomTemp))


@retry()
def _get_webapp_status():
  """Get the status from the webapp."""
  response = urllib2.urlopen(WEBAPP_URL + "get_status")
  data = json.load(response)
  return data['stop']


@retry()
def _update_webapp_status(pwd, target_temp, room_temp):
  """Update the status in the webapp."""
  url = WEBAPP_URL + "update_status"
  values = {
      'password': pwd,
      'target_temperature': target_temp,
      'room_temperature': room_temp,
  }
  data = urllib.urlencode(values)
  req = urllib2.Request(url, data)
  urllib2.urlopen(req)


### Methods to interact with the nest device.

@retry()
def set_temp(device, target_temp):
  device.target = nest_utils.f_to_c(target_temp)


@retry()
def get_curtemp(device):
  return nest_utils.c_to_f(device.temperature)


@retry()
def get_target_temp(device):
  return nest_utils.c_to_f(device.target)


@retry()
def _getDevice(login, password, serial):
  # Instantiate the nest object and login.
  napi = nest.Nest(login, password)
  # Find the device we want to control.
  device = None
  for d in napi.devices:
    if d._serial == serial:
      device = d
      break
  else:
    raise 'Could not find device with requested serial ID.'
  return device


if __name__ == '__main__':
  # Read nest parameters from the hidden files.
  login, password = _get_credentials()
  serial = _get_serial()
  webapp_password = _get_webapp_password()

  # Start the poller.
  while True:
    current_time = _getCurrentTime()
    device = _getDevice(login, password, serial)
    roomTemp = _getRoomTemperature()
    targetTemp = -1

    should_stop = _get_webapp_status()
    if should_stop:
      logger.info('Controlbot is turned off from the webapp.')
      # Update the webapp.
      _update_webapp_status(webapp_password, -1, roomTemp)
      # Sleep and continue.
      time.sleep(POLLING_FREQUENCY_SECS)
      continue

    for schedule in _get_schedules():
      if schedule.start_time <= current_time <= schedule.end_time:
        targetTemp = schedule.target_temp
        logger.info(
            'Schedule set from %s to %s with target temp %s is active' %
            (schedule.start_time, schedule.end_time, schedule.target_temp))

        if schedule.managed_by_nest:
          # This schedule is managed by nest, set it and let nest handle it.
          logger.info('This schedule is managed by nest, setting it to %s',
                      schedule.target_temp)
          set_temp(device, schedule.target_temp)
          continue

        logger.info('The room temperature is %s. Target is %s. Heating is %s',
                    roomTemp, schedule.target_temp, schedule.heat)
        if schedule.heat:
          # Set variables for the heating action.
          activate_nest = roomTemp < (
              schedule.target_temp - schedule.target_temp_range)
          outside_range = roomTemp >= schedule.target_temp
          step_towards_goal = get_curtemp(device) + 1
          step_away_from_goal = get_curtemp(device) - 1
        else:
          # Set variables for the cooling action.
          activate_nest = roomTemp > (
              schedule.target_temp + schedule.target_temp_range)
          outside_range = roomTemp <= schedule.target_temp
          step_towards_goal = get_curtemp(device) - 1.5
          step_away_from_goal = get_curtemp(device) + 1.5

        if activate_nest:
          logger.info('Nest needs to run.')
          logger.info(
              'Changing nest temperature to %s. The previous target '
              'temperature was %s', step_towards_goal, get_target_temp(device))
          set_temp(device, step_towards_goal)
        elif outside_range:
          logger.info('Desired room temperature %s reached. Setting nest away '
                      'from current %s.', roomTemp, get_curtemp(device))
          set_temp(device, step_away_from_goal)
        else:
          logger.info('The room temperature is in the range. Doing nothing.')

    # Update the webapp.
    _update_webapp_status(webapp_password, targetTemp, roomTemp)

    logger.info('The room temperature is %s. Nest curr temp is %s. '
                 'Nest target temp is %s', roomTemp, get_curtemp(device),
                 get_target_temp(device))
    logger.info('-' * 50)

    # Sleep before the next poll.
    time.sleep(POLLING_FREQUENCY_SECS)

