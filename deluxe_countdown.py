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
import textwrap

import typing
import collections
from dataclasses import dataclass

import obspython as obs

# We fill the combo box with "source-name (source-type)" strings.
# This sub pattern makes striking the following (source-type) simple.
sub_out_source_type_info = re.compile(r' \([^()]+\)').sub

@dataclass
class AnnotatedDuration:
    """
    Class containing a formatted duration string and its associated duration in seconds.
    """
    string: str
    seconds: float

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
        self.reset()

    def reset(self):
        """
        Reset the clock - only effective for duration-style countdowns.
        """

        self.reference_time = datetime.now()

    def get_time(self, time_format, hide_zero_time, round_up):
        """
        Get the countdown time as an AnnotatedDuration
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

        return AnnotatedDuration(string=_string, seconds=_duration)

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

@dataclass
class Preference:
    """
    Class representing a script configuration setting's value and UI.

    A Preference can be automatically translated into an OBS widget based on
    its type using the OBS properties API.

    It also stores the value selected, updated via callbacks.  If OBS provided
    a means to query the current value directly from an obs_property_t, this
    class would not be required.
    """

    key: str  # Key used to store the Preference in a dict
    name: str  # Display name used in the widget
    default: typing.Any  # default value of the Preference (set via the "Defaults" button)
    type: typing.Any  # obs.OBS_* type specifier
    tooltip: typing.Optional[str] = None  # Detailed description of the Preference

    # list_items can be a list of items, or a function to call to fill in the
    # list items into the passed in obs_property_t object.
    list_items: typing.Union[None,
                             list[str],
                             collections.abc.Callable[[any], None]] = None

    # Function to call on button press, for buttons only
    callback: typing.Optional[collections.abc.Callable] = None
    induce_reset: bool = False # When true, reset should be called when the user modifies this preference
    cur_value: typing.Any = None # current value of the Preference (reset via the "Defaults" button)

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

        _p = {}

        def add_pref(key, name, default, *args, **kwargs):
            _p[key] = Preference(key, name, default, *args, **kwargs, cur_value=default)

        add_pref('clock_type', 'Clock Type', 'Duration', self.OBS_COMBO,
                 list_items=['Duration', 'Date/Time'],
                 tooltip="""
            Choose the type of countdown timer:
            * Duration: Count down to the last timer reset
            * Date/Time: Count down to the given set point in time
        """)

        add_pref('format', 'Format', '%H:%M:%S', self.OBS_TEXT,
                 tooltip="""
            Display format for the countdown timer, using strftime-style % codes:
              %d - days
              %H - hours in 24-hour time format
              %M - minutes
              %S - seconds
        """)

        add_pref('hide_zero_units', 'Hide Zero Units', False, self.OBS_BOOLEAN,
                 tooltip="""
            Eliminate highest order clauses involving zero units.
            For example, if Format is %H:%M:%S, but hours is 0 and minutes is not,
            the resulting output will be $M:%S.
        """)

        add_pref('round_up', 'Round Up', False, self.OBS_BOOLEAN,
                 tooltip="""
            Round up to the next smallest unit when the remaining time falls in the middle.
        """)

        add_pref('duration', 'Duration', '1000', self.OBS_TEXT,
                 induce_reset=True,
                 tooltip="""
            Set the countdown duration to use in minutes, or %H:%M:%S format.
        """)

        add_pref('date', 'Date', 'TODAY', self.OBS_TEXT,
                 induce_reset=True,
                 tooltip="""
            Set the target date for use with the Date/Time Clock Type
            The format is %Y:%m:%d (ISO style), or TODAY
        """)

        add_pref('time', 'Time', '12:00:00 pm', self.OBS_TEXT,
                 induce_reset=True,
                 tooltip="""
            Set the target time for use with the Date/Time Clock Type
            The format is "%H:%M:%S" for 24-hour time, or append am or pm for 12 hour time.
        """)

        add_pref('end_text', 'End Text', 'Live Now!', self.OBS_TEXT,
                 tooltip="""
            The text to display in the selected Text Source after the timer has expired.
        """)

        add_pref('text_source', 'Text Source', '', self.OBS_COMBO,
                 list_items=fill_sources_property_list,
                 tooltip="""
            The OBS text source into which the countdown timer will render.
            Add a text source to your scene, click the "Reload Text Source list" button,
            then select your new source from the dropdown.
            Note the countdown timer will replace the contents of the selected text source.
        """)

        add_pref('reset_timer', 'Reset Timer', '', self.OBS_BUTTON,
                 callback=reset_button_clicked,
                 tooltip="""
            Reset the timer to start from the given duration
            (Relevant if the Duration Clock Type is selected)
        """)

        return _p

    def refresh_properties(self, settings):
        """
        Refresh the script state to match the given settings from the user UI update

        Returns True if any script_state property with induce_reset set is modified.
        """
        _induce_reset = False

        for _k, _v in self.properties.items():
            _prior_value = _v.cur_value
            _v.cur_value = self.get_value(_k, settings)

            if _v.induce_reset and _prior_value != _v.cur_value:
                _induce_reset = True

        return _induce_reset

    def get_value(self, pref_name, settings=None):
        """
        Updates and gets the current value of the requested preference using the
        provided obs_settings_t settings object if it is not None.

        Returns the resulting value of the preference.
        """

        if settings:

            _fn = obs.obs_data_get_string

            if self.properties[pref_name].type == self.OBS_BOOLEAN:
                _fn = obs.obs_data_get_bool

            _value = _fn(settings, pref_name)
            self.properties[pref_name].cur_value = _value

        return self.properties[pref_name].cur_value

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

#------------------------------------------------
# Handlers and helpers for OBS callback functions
#------------------------------------------------

def blkfmt(s):
    """
    Formats a triple-quoted string for display as a tooltip or discription:

    * Removes common leading whitespace (via textwrap.dedent)
    * Then removes leading and trailing whitespace via str.strip
    """
    return textwrap.dedent(s).strip()

def set_prop_tooltip(prop, text):
    """
    Sets the given text as the prop's tooltip, after calling blkfmt on the text.
    """
    if text:
        obs.obs_property_set_long_description(prop, blkfmt(text))

def fill_sources_property_list(list_property):
    """
    Update the list of Text Sources based on those currently known to OBS.
    Use this when you want to display the countdown in a newly added source.
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

def update_text():
    """
    Update the text with the passed time string
    """

    _hide_zero_units = script_state.properties['hide_zero_units'].cur_value
    _format = script_state.properties['format'].cur_value
    _round_up = script_state.properties['round_up'].cur_value
    _annotated_duration = script_state.clock.get_time(_format, _hide_zero_units, _round_up)

    _source_name = script_state.get_text_source_name()

    if not _source_name:
        return

    _text = _annotated_duration.string

    if _annotated_duration.seconds == 0:
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
        #print(f"activate_signal() called with source '{sig_source_name}'.  active: {_is_active}")

        target_text_source_name = script_state.get_text_source_name()
        if (sig_source_name == target_text_source_name):
            #print(f"activate_signal() source matches '{target_text_source_name}'")
            activate(_is_active)

def restart_timer(induce_reset=True):
    """
    Restart the timer given the current script_state settings
    """

    activate(False)

    if induce_reset:
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

    restart_timer(induce_reset=True)

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

#-----------------------
# OBS callback functions
#-----------------------

def script_update(settings):
    """
    Called when the user updates settings
    """

    _induce_reset = script_state.refresh_properties(settings)

    _type = script_state.properties['clock_type'].cur_value

    _is_duration = _type == 'Duration'

    if _is_duration:

        _interval = script_state.properties['duration'].cur_value
        script_state.clock.set_duration(_interval)

    else:
        _date = script_state.properties['date']
        _time = script_state.properties['time']
        script_state.clock.set_date_time(_date, _time)

    restart_timer(_induce_reset)

def script_description():
    """
    Returns the Description text to display in the script settings pane.
    (OBS main script callback)
    """
    return blkfmt("""
        Display a countdown clock in an OBS text source.

        Choose whether to count down a given duration of time,
        or count down to a specified target date and time.
    """)

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
                set_prop_tooltip(_p, _fill_prop_list.__doc__)

            else:

                for _item in _v.list_items:
                    obs.obs_property_list_add_string(_v.prop_ref, _item, _item)

        elif _v.type == script_state.OBS_BOOLEAN:

                _v.prop_ref = obs.obs_properties_add_bool(props, _k, _v.name)

        elif _v.type == script_state.OBS_BUTTON:

            _v.prop_ref = obs.obs_properties_add_button(props, _k, _v.name, _v.callback)

        else:

            _v.prop_ref = obs.obs_properties_add_text(props, _k, _v.name, _v.type)

        set_prop_tooltip(_v.prop_ref, _v.tooltip)

    script_state.obs_properties = props

    return props

def script_save(settings):
    """
    Save state for script
    """

    _hotkey_save_array = obs.obs_hotkey_save(script_state.hotkey_id)
    obs.obs_data_set_array(settings, "reset_hotkey", _hotkey_save_array)
    obs.obs_data_array_release(_hotkey_save_array)

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
        "reset_timer_thingy", "Reset Timer", restart_timer)

    _hotkey_save_array = obs.obs_data_get_array(settings, "reset_hotkey")
    obs.obs_hotkey_load(_hotkey_id, _hotkey_save_array)
    obs.obs_data_array_release(_hotkey_save_array)

#--------------------
# Script state global
#--------------------

# We must wait to call the State() constructor until after its callback
# handlers have been defined, so this is done at the end.

script_state = State()
