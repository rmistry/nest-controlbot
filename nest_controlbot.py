#! /usr/bin/python

"""Bot that adjusts the Nest thermostat using a JSON schedule.

This is currently only setup for heat since it was winter when I wrote it.
"""


import datetime
import json
import logging
import os
import pytz
import time
import urllib
import urllib2

from nest_thermostat import Nest

# Below is from https://github.com/timofurrer/w1thermsensor
from w1thermsensor import W1ThermSensor


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
logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s',
                    filename='nest_controlbot.log', level=logging.INFO)
logger = logging.getLogger('nest_controlbot')


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


def _getRoomTemperature(n):
  """Returns the room temperature as reported from Raspberry Pi."""
  sensor = W1ThermSensor()
  roomTemp = sensor.get_temperature(W1ThermSensor.DEGREES_F)
  return float("{0:.2f}".format(roomTemp))
  # Uncomment the below while testing.
  # return n.get_curtemp()


def _get_webapp_status():
  """Get the status from the webapp."""
  response = urllib2.urlopen(WEBAPP_URL + "get_status")
  data = json.load(response)
  return data['stop']


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


if __name__ == '__main__':
  # Read nest parameters from the hidden files.
  login, password = _get_credentials()
  serial = _get_serial()
  webapp_password = _get_webapp_password()

  # Start the poller.
  while True:
    current_time = _getCurrentTime()
    # Instantiate the nest object and login.
    n = Nest(login, password, serial)
    n.login()
    n.get_status()
    roomTemp = _getRoomTemperature(n)
    targetTemp = -1

    should_stop = _get_webapp_status()
    if should_stop:
      logging.info('Controlbot is turned off from the webapp.')
      # Update the webapp.
      _update_webapp_status(webapp_password, -1, roomTemp)
      # Sleep and continue.
      time.sleep(POLLING_FREQUENCY_SECS)
      continue

    for schedule in _get_schedules():
      if schedule.start_time <= current_time <= schedule.end_time:
        targetTemp = schedule.target_temp
        logging.info(
            'Schedule set from %s to %s with target temp %s is active' %
            (schedule.start_time, schedule.end_time, schedule.target_temp))

        if schedule.managed_by_nest:
          # This schedule is managed by nest, set it and let nest handle it.
          logging.info('This schedule is managed by nest, setting it to %s',
                       schedule.target_temp)
          n.set_temperature(schedule.target_temp)
          continue

        logging.info('The room temperature is %s. Target is %s. Heating is %s',
                     roomTemp, schedule.target_temp, schedule.heat)
        if schedule.heat:
          # Set variables for the heating action.
          activate_nest = roomTemp < (
              schedule.target_temp - schedule.target_temp_range)
          outside_range = roomTemp >= schedule.target_temp
          step_towards_goal = n.get_curtemp() + 1
          step_away_from_goal = n.get_curtemp() - 1
        else:
          # Set variables for the cooling action.
          activate_nest = roomTemp > (
              schedule.target_temp + schedule.target_temp_range)
          outside_range = roomTemp <= schedule.target_temp
          step_towards_goal = n.get_curtemp() - 1
          step_away_from_goal = n.get_curtemp() + 1

        if activate_nest:
          logging.info('Nest needs to run.')
          logging.info(
              'Changing nest temperature to %s. The previous target '
              'temperature was %s', step_towards_goal, n.get_target())
          n.set_temperature(step_towards_goal)
        elif outside_range:
          logging.info('Desired room temperature %s reached. Setting nest away '
                       'from current %s.', roomTemp, n.get_curtemp())
          n.set_temperature(step_away_from_goal)
        else:
          logging.info('The room temperature is in the range. Doing nothing.')

    # Update the webapp.
    _update_webapp_status(webapp_password, targetTemp, roomTemp)

    logging.info('The room temperature is %s. Nest curr temp is %s. '
                 'Nest target temp is %s', roomTemp, n.get_curtemp(),
                 n.get_target())
    logging.info('-' * 50)

    # Sleep before the next poll.
    time.sleep(POLLING_FREQUENCY_SECS)

