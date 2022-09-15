#-----------------------------------------------------------------------
# Copyright (C) 2020 by Joel Graff <monograff76@gmail.com>
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#-----------------------------------------------------------------------

"""
Enhanced countdown script for use with OBS, based on lua-based
script included with OBS.

https://github.com/obsproject/obs-studio/blob/b2302902a3b3e1cce140a6417f4c5e490869a3f2/UI/frontend-plugins/frontend-tools/data/scripts/countdown.lua
"""

from datetime import datetime, timedelta
import time
import re

from types import SimpleNamespace
from copy import deepcopy

import obspython as obs

# We fill the combo box with "source-name (source-type)" strings.
# This sub pattern makes striking the following (source-type) simple.
sub_out_source_type_info = re.compile(r' \([^()]+\)').sub

class Clock():
    """
    Class to manage the current clock state
    """

    def __init__(self):
        """
        Constructor
        """

        self.reference_time = None
        self.target_time = None
        self.duration = None
        self.mode ='duration'

    def reset(self):
        """
        Reset the clock - only effective for duration-style countdowns.
        """

        self.reference_time = datetime.now()

    def get_time(self, time_format, hide_zero_time, round_up):
        """
        Get the countdown time as a string
        """

        _current_time = datetime.now()
        _delta = timedelta(days=0, seconds=0)
        _duration = 0

        #get clock time by duration
        if self.mode == 'duration':

            _delta = _current_time - self.reference_time
            _duration = self.duration - _delta.total_seconds()
            _delta = timedelta(seconds=_duration)

            if _duration < 0:
                _duration = 0

        #get clock time by target time
        elif self.target_time and _current_time < self.target_time:

            _delta = self.target_time - _current_time
            _duration = _delta.total_seconds()

        _fmt = time_format.split('%')
        _fmt_2 = []
        _result = ''

        #prepare time formatting
        for _i, _v in enumerate(_fmt):

            if not _v:
                continue

            #get the first letter of the current unit
            _x = _v[:2].lower()

            #prepend the result with time formatting for days
            if 'd' in _x:

                if not (hide_zero_time and _delta.days == 0):
                    _result = str(_delta.days) + _v[1:]

                continue

            #if hiding zero time units, test for hour and minute conditions
            if hide_zero_time:

                if 'h' in _x and _duration < 3600:

                    #skip unless hours is last in the format string
                    if 'h' not in _fmt[-1][:2].lower():
                        continue

                if 'm' in _x and _duration < 60:

                    #do not skip if hours are still visible
                    if not _fmt or 'h' not in _fmt[-1][:2].lower():

                        #skip unless minutes are last in the format string
                        if _fmt[-1][0].lower() != 'm':
                            continue

            _fmt_2.append(_v)

        _duration_2 = _duration

        #round up the last time unit if required
        if round_up:

            _c = 0
            _u = _fmt_2[-1][:2].lower()

            if 'd' in _u:
                _c = 86400

            elif 'h' in _u:
                _c = 3600

            elif 'm' in _u:
                _c = 60

            elif 's' in _u:
                _c = 1

            _duration_2 += _c

        time_format = '%'.join([''] + _fmt_2)

        _string = _result + time.strftime(time_format, time.gmtime(_duration_2))

        return SimpleNamespace(
            string = _string, seconds = _duration)

    def set_duration(self, interval):
        """
        Set the duration of the timer
        """

        self.mode = 'duration'
        self.duration = self.update_duration(interval)

    def set_date_time(self, target_date, target_time):
        """
        Set the target date / time of the timer
        """

        self.mode = 'date/time'

        try:
            self.duration = self.update_date_time(target_date, target_time)
        except:
            self.duration = 0

    def update_duration(self, interval):
        """
        Calculate the number of seconds for the specified duration
        Format may be:
        - Integer in minutes
        - HH:MM:SS as a string
        """

        interval = interval.split(':')[-3:]
        _seconds = 0

        #Only one element - duration specified in minutes
        if len(interval) == 1:

            if not interval[0]:
                interval[0] = 0

            return float(interval[0]) * 60.0

        #otherwise, duration in HH:MM:SS format
        for _i, _v in enumerate(interval[::-1]):\

            if not _v:
                continue

            _m = 60 ** _i
            _seconds += int(_v) * _m

        return _seconds

    def update_date_time(self, target_date, target_time):
        """
        Set the target date and time
        """

        if target_time is None:
            return

        #test for 12-hour format specification
        _am_pm = target_time.find('am')
        _is_pm = False

        if _am_pm == -1:
            _am_pm = target_time.find('pm')
            _is_pm = _am_pm > -1

        #strip 'am' or 'pm' text
        if _am_pm != -1:
            target_time = target_time[:_am_pm]

        target_time = [int(_v) for _v in target_time.split(':')]

        if len(target_time) == 2:
            target_time += [0]

        #adjust 12-hour pm to 24-hour format
        if _is_pm:
            if target_time[0] < 12:
                target_time[0] += 12

        elif target_time[0] == 12:
                target_time[0] = 0

        if target_time[0] > 23:
            target_time[0] = 0

        _target = None
        _now = datetime.now()

        #calculate date
        if target_date == 'TODAY':
            target_date = [_now.month, _now.day, _now.year]

        else:
            target_date = [int(_v) for _v in target_date.split('/')]

        self.target_time = datetime(
                target_date[2], target_date[0], target_date[1],
                target_time[0], target_time[1], target_time[2]
        )

def fill_sources_property_list(list_property):
    """
    Get list of text sources and fill them into the given property list
    """

    obs.obs_property_list_clear(list_property)
    _sources = obs.obs_enum_sources()

    for _source in _sources:

        source_type = obs.obs_source_get_id(_source)
        if source_type.startswith("text"):

            _list_item = f"{obs.obs_source_get_name(_source)} ({source_type})"
            print(f"Adding source '{_list_item}'")
            obs.obs_property_list_add_string(list_property, _list_item, _list_item)

    obs.source_list_release(_sources)

    _has_items = obs.obs_property_list_item_count(list_property)
    # Insert a dummy item so the script doesn't automatically select the first
    # item on the list and clobber its contents.
    obs.obs_property_list_insert_string(list_property, 0,
        f'<None {"selected" if _has_items else "available"}>', '')

    # When called from script_update() or via obs_property_set_modified_callback(),
    # returning True induces OBS to regenerate the properties UI widgets.
    return True

class State():
    """
    Script state class
    """

    def __init__(self):
        """
        Constructor
        """

        #constants
        self.OBS_COMBO = obs.OBS_COMBO_TYPE_LIST
        self.OBS_TEXT = obs.OBS_TEXT_DEFAULT
        self.OBS_BUTTON = 'OBS_BUTTON'
        self.OBS_BOOLEAN = 'OBS_BOOLEAN'

        #other global vars for OBS callbacks
        self.clock = Clock()
        self.hotkey_id = 0
        self.activated = False
        self.properties = self.build_properties()
        self.obs_properties = None

    def build_properties(self):
        """
        Build dict defining script properties
        """

        #lambda to return a SimpleNamespace object for OBS data properties
        # items can be a list of items, or a function to call to get the list
        # of items to use on each call to script_properties().
        _fn = lambda p_name, p_default, p_type, p_items=None:\
            SimpleNamespace(
                name=p_name, default=p_default, type=p_type, list_items=p_items,
                cur_value=p_default, prop_ref=None)

        _p = {}

        _p['clock_type'] = _fn(
            'Clock Type', 'Duration', self.OBS_COMBO,
            ['Duration', 'Date/Time']
        )
        _p['format'] = _fn('Format', '%H:%M:%S', self.OBS_TEXT)
        _p['hide_zero_units'] = _fn('Hide Zero Units', False, self.OBS_BOOLEAN)
        _p['round_up'] = _fn('Round Up', False, self.OBS_BOOLEAN)
        _p['duration'] = _fn('Duration', '1000', self.OBS_TEXT)
        _p['date'] = _fn('Date', 'TODAY', self.OBS_TEXT)
        _p['time'] = _fn('Time', '12:00:00 pm', self.OBS_TEXT)
        _p['end_text'] = _fn('End Text', 'Live Now!', self.OBS_TEXT)

        _p['text_source'] = _fn('Text Source', '', self.OBS_COMBO,
                                fill_sources_property_list)

        return _p

    def refresh_properties(self, settings):
        """
        Refresh the script state to match the given settings from the user UI update
        """

        for _k, _v in self.properties.items():
            _v.cur_value = self.get_value(_k, settings)

    def get_value(self, source_name, settings=None):
        """
        Get the value of the source using the provided settings
        If settings is None, previously-provided settings will be used
        """

        if settings:

            _fn = obs.obs_data_get_string

            if self.properties[source_name].type == self.OBS_BOOLEAN:
                _fn = obs.obs_data_get_bool

            _value = _fn(settings, source_name)
            self.properties[source_name].cur_value = _value

            return _fn(settings, source_name)

        return self.properties[source_name].cur_value

    def set_value(self, source_name, prop, value):
        """
        Dead code, seems broken

        Set the value of the source using the provided settings
        If settings is None, previously-provided settings will be used
        """

        _settings = obs.obs_data_create()
        _source = obs.obs_get_source_by_name(source_name)

        obs.obs_data_set_string(_settings, prop, value)
        obs.obs_source_update(_source, _settings)
        obs.obs_data_release(_settings)
        obs.obs_source_release(_source)

        self.properties[source_name].cur_value = value

    def get_text_source_name(self):
        """
        Get the name of the text source without the appended type information.
        """
        return sub_out_source_type_info("", self.get_value('text_source'))

script_state = State()

#-----------------------
# OBS callback functions
#-----------------------

def update_text():
    """
    Update the text with the passed time string
    """

    _hide_zero_units = script_state.properties['hide_zero_units'].cur_value
    _format = script_state.properties['format'].cur_value
    _round_up = script_state.properties['round_up'].cur_value
    _time = script_state.clock.get_time(_format, _hide_zero_units, _round_up)

    _source_name = script_state.get_text_source_name()

    if not _source_name:
        return

    _text = _time.string

    if _time.seconds == 0:
        obs.remove_current_callback()
        _text = script_state.get_value('end_text')

    _settings = obs.obs_data_create()
    _source = obs.obs_get_source_by_name(_source_name)

    obs.obs_data_set_string(_settings, 'text', _text)
    obs.obs_source_update(_source, _settings)
    obs.obs_data_release(_settings)
    obs.obs_source_release(_source)

def activate(activating):
    """
    Activate / deactivate timer based on source text object state
    """

    # When the state wouldn't change, return immediately.
    if script_state.activated == activating:
        return

    script_state.activated = activating

    #add the timer if becoming active
    if activating:

        print("activating")
        update_text()
        obs.timer_add(update_text, 1000)

    #remove if going inactive
    else:
        print("deactivating")
        obs.timer_remove(update_text)

def handle_source_visibility_signal(cd):
    """
    Called when source is activated / deactivated
    """
    _source = obs.calldata_source(cd, "source")
    _is_active = obs.obs_source_active(_source)

    if _source:
        sig_source_name = obs.obs_source_get_name(_source)
        print(f"activate_signal() called with source '{sig_source_name}'.  active: {_is_active}")

        target_text_source_name = script_state.get_text_source_name()
        if (sig_source_name == target_text_source_name):
            print(f"activate_signal() source matches '{target_text_source_name}'")
            activate(_is_active)

def restart_timer():
    """
    Restart the timer given the current script_state settings
    """

    activate(False)
    script_state.clock.reset()

    _source_name = script_state.get_text_source_name()
    _source = obs.obs_get_source_by_name(_source_name)

    if _source:
        _is_active = obs.obs_source_active(_source)
        obs.obs_source_release(_source)
        activate(_is_active)

def reset_button_clicked(props, p):
    """
    Callback for the Restart Timer button
    """

    restart_timer()
    return False

def script_update(settings):
    """
    Called when the user updates settings
    """

    script_state.refresh_properties(settings)

    _type = script_state.properties['clock_type'].cur_value

    _is_duration = _type == 'Duration'

    if _is_duration:

        _interval = script_state.properties['duration'].cur_value
        script_state.clock.set_duration(_interval)

    else:
        _date = script_state.properties['date']
        _time = script_state.properties['time']
        script_state.clock.set_date_time(_date, _time)

    restart_timer()

def script_description():
    """
    Script description
    """
    return """
    Countdown clock for a duration or to a date/time.\n
    Clock Type\tCount from now (Duration) or to target (Time)
    Format\tOutput time format
    Show Units\tShow time units in output
    Duration\tInteger (sec) or HH:MM:SS
    Date\t\tMM/DD/YYYY or TODAY
    Time\t\tHH:MM:SS [am/pm] for 12-hour
    End Text\tShown after countdown
    Text Source\tSource for start / end text
    """

def script_defaults(settings):
    """
    Set default values for properties
    """

    for _k, _v in script_state.properties.items():

        if _v.type not in [script_state.OBS_BUTTON, script_state.OBS_BOOLEAN]:
            obs.obs_data_set_default_string(settings, _k, _v.default)

    for _k, _v in script_state.properties.items():

        if _v.type not in [script_state.OBS_BUTTON, script_state.OBS_BOOLEAN]:
            _v.cur_value = obs.obs_data_get_string(settings, _k)

    if script_state.properties['clock_type'] == 'Duration':

        script_state.clock.set_duration(
            script_state.properties['duration'].cur_value)

    else:

        script_state.clock.set_date_time(
            script_state.properties['date'].cur_value,
            script_state.properties['time'].cur_value
        )

def script_properties():
    """
    Create properties for script settings dialog
    """

    print("OBS called script_properties()")

    props = obs.obs_properties_create()

    for _k, _v in script_state.properties.items():

        if _v.type == script_state.OBS_COMBO:

            _v.prop_ref = obs.obs_properties_add_list(
                props, _k, _v.name, _v.type, obs.OBS_COMBO_FORMAT_STRING)

            if callable(_v.list_items):

                # _v.list_items is a function that fills the property list itself
                _fill_prop_list = _v.list_items
                _fill_prop_list(_v.prop_ref)

                # Add a button to refresh the property list
                # There is no way currently in OBS to update the properties
                # widget except through a button callback or through a
                # obs_property_set_modified_callback callback, each of which
                # must retutrn True to update the widgets.
                _p = obs.obs_properties_add_button(
                    props, f'reload_{_k}', f'Reload {_v.name} list',
                    lambda props, p: True if _fill_prop_list(_v.prop_ref) else True)

            else:

                for _item in _v.list_items:
                    obs.obs_property_list_add_string(_v.prop_ref, _item, _item)

        elif _v.type == script_state.OBS_BOOLEAN:

                obs.obs_properties_add_bool(props, _k, _v.name)

        else:

            obs.obs_properties_add_text(props, _k, _v.name, _v.type)

    obs.obs_properties_add_button(
        props, 'restart_timer', 'Restart Timer', reset_button_clicked)

    script_state.obs_properties = props

    return props

def script_save(settings):
    """
    Save state for script
    """

    _hotkey_save_array = obs.obs_hotkey_save(script_state.hotkey_id)
    obs.obs_data_set_array(settings, "reset_hotkey", _hotkey_save_array)
    obs.obs_data_array_release(_hotkey_save_array)

def print_signal(signal_name, cd):
    """
    For debugging OBS signalling - wire up in script_load with
    obs.signal_handler_connect_global(_sh, print_signal)
    """

    if signal_name.startswith('source'):
        source = obs.calldata_source(cd, "source")
        source_name = obs.obs_source_get_name(source)
        source_type = obs.obs_source_get_id(source)
        print(f"Signal '{signal_name}' raised for source '{source_name}' ({source_type})")

    else:
        print(f"Signal raised: '{signal_name}'")

def script_load(settings):
    """
    Connect hotkey and activation/deactivation signal callbacks
    """

    _sh = obs.obs_get_signal_handler()
    obs.signal_handler_connect(_sh, "source_hide", handle_source_visibility_signal)
    obs.signal_handler_connect(_sh, "source_show", handle_source_visibility_signal)
    # source_rename (ptr source, string new_name, string prev_name)
    obs.signal_handler_connect(_sh, "source_rename", handle_source_visibility_signal)
    #obs.signal_handler_connect(_sh, "source_create", handle_source_create)
    #obs.signal_handler_connect(_sh, "source_destroy", handle_source_destroy)
    #obs.signal_handler_connect_global(_sh, print_signal)

    _hotkey_id = obs.obs_hotkey_register_frontend(
        "reset_timer_thingy", "Restart Timer", restart_timer)

    _hotkey_save_array = obs.obs_data_get_array(settings, "reset_hotkey")
    obs.obs_hotkey_load(_hotkey_id, _hotkey_save_array)
    obs.obs_data_array_release(_hotkey_save_array)
