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
from contextlib import contextmanager

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

    def set_date_time(self, target_date, target_time):
        """
        Set the target date and time
        """

        print("Setting date/time")
        self.mode = 'date/time'
        if target_time is None:
            print("Target time is None")
            return

        # handle "am/pm" 12-hour format specification
        _is_am = "am" in target_time
        _is_pm = "pm" in target_time

        if _is_am or _is_pm:
            # strip 'am' or 'pm' text
            target_time = re.sub(r'\s*[ap]m\b', '', target_time, re.IGNORECASE)

        target_time = [int(_v) for _v in target_time.split(':')]

        # Add time units from the least significant if unspecified
        while len(target_time) < 3:
            target_time.append(0)

        #adjust 12-hour pm to 24-hour format
        if _is_pm and target_time[0] < 12:
            target_time[0] += 12

        elif _is_am and target_time[0] == 12:
            target_time[0] = 0

        _now = datetime.now()

        #calculate date
        _offset = timedelta(0)

        if target_date.upper() == 'TOMORROW':
            _offset = timedelta(days=1)

        if target_date.upper() in 'TODAY TOMORROW'.split():
            target_date = [_now.year, _now.month, _now.day]

        else:
            target_date = [int(_v) for _v in target_date.split('/')]

        self.target_time = datetime(*target_date, *target_time) + _offset
        print(f"Set target to {self.target_time}")

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
        self.OBS_INFO = 'OBS_INFO'

        #other global vars for OBS callbacks
        self.clock = Clock()
        self.hotkey_id = 0
        self.activated = False
        self.prefs = self.init_preferences()
        self.obs_properties = None

    def init_preferences(self):
        """
        Specifies the dict of script preferences.

        This is used to build the properties widget via the main OBS
        script_properties() callback, as well as to mirror the state of those
        properties settings for easier access by the script.
        """

        _p = {}

        def add_pref(key, name, default, *args, **kwargs):
            _p[key] = Preference(key, name, default, *args, **kwargs, cur_value=default)

        add_pref('text_source', 'Text Source', '', self.OBS_COMBO,
                 list_items=fill_sources_property_list,
                 tooltip="""
            The OBS text source into which the countdown timer will render.
            Add a text source to your scene, click the "Reload Text Source list" button,
            then select your new source from the dropdown.
            Note the countdown timer will replace the contents of the selected text source.
        """)

        add_pref('end_text', 'End Text', 'Live Now!', self.OBS_TEXT,
                 tooltip="""
            The text to display in the selected Text Source after the timer has expired.
        """)

        add_pref('reset_timer', 'Reset Timer', '', self.OBS_BUTTON,
                 callback=reset_button_clicked,
                 tooltip="""
            Reset the timer to start from the given duration
            (Relevant if the Duration Clock Type is selected)
        """)

        add_pref('hide_zero_units', 'Hide Zero Units', True, self.OBS_BOOLEAN,
                 tooltip="""
            Eliminate highest order clauses involving zero units.
            For example, if Format is %H:%M:%S, but hours is 0 and minutes is not,
            the resulting output will be %M:%S.
        """)

        add_pref('round_up', 'Round Up', True, self.OBS_BOOLEAN,
                 tooltip="""
            Round up to the next smallest unit when the remaining time falls in the middle.
        """)

        add_pref('format', 'Format', '%H:%M:%S', self.OBS_TEXT,
                 tooltip="""
            Display format for the countdown timer, using strftime-style % codes:
              %d - days
              %H - hours in 24-hour time format
              %M - minutes
              %S - seconds
        """)

        add_pref('clock_type', 'Clock Type', 'Duration', self.OBS_COMBO,
                 list_items=['Duration', 'Date/Time'],
                 tooltip="""
            Choose the type of countdown timer:
            * Duration: Count down to the last timer reset
            * Date/Time: Count down to the given set point in time
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
            The format is %Y/%m/%d (ISO style), TODAY, or TOMORROW
        """)

        add_pref('time', 'Time', '12:00:00 pm', self.OBS_TEXT,
                 induce_reset=True,
                 tooltip="""
            Set the target time for use with the Date/Time Clock Type
            The format is "%H:%M:%S" for 24-hour time, or append am or pm for 12 hour time.
        """)

        add_pref('last_update', 'Last Update', '<updated>', self.OBS_INFO,
                 tooltip="<not updated>")

        return _p

    def refresh_preferences(self, settings):
        """
        Refresh the script state to match the given settings from the user UI update

        Returns True if any script_state property with induce_reset set is modified.
        """
        _induce_reset = False

        for _pref_key, _pref in self.prefs.items():
            _prior_value = _pref.cur_value
            _pref.cur_value = self.get_value(_pref_key, settings)

            if _pref.induce_reset and _prior_value != _pref.cur_value:
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

            if self.prefs[pref_name].type == self.OBS_BOOLEAN:
                _fn = obs.obs_data_get_bool

            _value = _fn(settings, pref_name)
            self.prefs[pref_name].cur_value = _value

        return self.prefs[pref_name].cur_value

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

@contextmanager
def auto_release_source(source):
    """
    Manages the OBS source of the given _name.  During execution of the with block,
    the bound variable refers to the referenced source.  Afterwards, the source is released.
    """
    if isinstance(source, str):
        source = obs.obs_get_source_by_name(source)

    try:
        yield source

    finally:
        if source:
            obs.obs_source_release(source)

def set_prop_tooltip(prop, text):
    """
    Sets the given text as the prop's tooltip, after calling blkfmt on the text.
    """
    if prop and text:
        obs.obs_property_set_long_description(prop, blkfmt(text))

def set_last_update_timestamp(props, reason):
    """
    Sets the "Last Update" info field with the current timestamp
    and a parenthesized reason explaining why the field was updated.
    """

    _last_update_prop = obs.obs_properties_get(props, "last_update")
    if _last_update_prop:
        obs.obs_property_set_long_description(_last_update_prop,
                                              f"{datetime.now()}\n({reason})")

def add_combo_list_regeneration_button(props, combo_prop, regen_fn):
    """
    Adds a button to refresh the given combo_prop list via the given regen_fn.

    Note OBS has no way to update the properties UI except through a button
    callback or through a obs_property_set_modified_callback callback, each of
    which must retutrn True to update the widgets.

    The regen_fn must take 3 arguments:
        cd_props - an obs_properties_t reference to all script properties
        combo_prop - the reference to the combo list obs_property_t
        reason - a string describing why the regen_fn is being called

    The created button will have a tooltip set from the regen_fn.__doc__ string,
    and the reason passed in will indicate that the reload button was pressed.

    The button callback is created such that the properties UI widgets will be
    refreshed.
    """

    _combo_prop_setting_name = obs.obs_property_name(combo_prop)
    _combo_prop_display_name = obs.obs_property_description(combo_prop)

    _p = obs.obs_properties_add_button(
        props, f'reload_{_combo_prop_setting_name}', f'Reload {_combo_prop_display_name} list',
        lambda cd_props, cd_prop: True if regen_fn(cd_props, combo_prop, f"reload_{_combo_prop_setting_name} button") else True)

    set_prop_tooltip(_p, regen_fn.__doc__)

def fill_sources_property_list(props, list_property, reason):
    """
    Updates the string combo box list referenced by combo_prop.

    This function lists all available text-type sources currently configured
    in OBS, and populates the combo box with those names.

    Returns True to indicate the script properties UI widgets should be
    redrawn.  (This only applies when this function is called as a callback
    for a button or as registered via obs_property_set_modified_callback.)
    """

    obs.obs_property_list_clear(list_property)
    _sources = obs.obs_enum_sources()

    for _source in _sources:

        _source_type = obs.obs_source_get_id(_source)
        if _source_type.startswith("text"):

            _source_name = obs.obs_source_get_name(_source)
            _list_item = f"{_source_name} ({_source_type})"
            #print(f"Adding source '{_list_item}'")
            obs.obs_property_list_add_string(list_property, _list_item, _source_name)

    obs.source_list_release(_sources)

    _has_items = obs.obs_property_list_item_count(list_property)
    # Insert a dummy item so the script doesn't automatically select the first
    # item on the list and clobber its contents.
    obs.obs_property_list_insert_string(list_property, 0,
        f'<None {"selected" if _has_items else "available"}>', '')

    set_last_update_timestamp(props, reason)

    # When called from a button callback or via obs_property_set_modified_callback(),
    # returning True induces OBS to regenerate the properties UI widgets.
    return True

def update_text():
    """
    Update the text with the passed time string
    """

    _hide_zero_units = script_state.prefs['hide_zero_units'].cur_value
    _format = script_state.prefs['format'].cur_value
    _round_up = script_state.prefs['round_up'].cur_value
    _annotated_duration = script_state.clock.get_time(_format, _hide_zero_units, _round_up)

    _source_name = script_state.get_value('text_source')

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

def handle_source_visibility_signal(signal_name, cd):
    """
    Called when a source is changed such that we should consider activating or
    deactivating the countdown timer.
    """
    _cd_source = obs.calldata_source(cd, "source")

    def _log(msg):
        _name = "<unknown>"
        if _cd_source:
            _name = obs.obs_source_get_name(_cd_source)
        #print(f"[{datetime.now()}] Handling {signal_name}({_name}): {msg}")

    if not _cd_source:

        _log(f"Ignoring: callback data had no source")
        return

    # If the passed in data isn't a text source, ignore the signal
    _cd_source_type = obs.obs_source_get_id(_cd_source)
    if not _cd_source_type.startswith("text"):

        _log(f"Ignoring non-text callback data source of type [{_cd_source_type}]")
        return

    # Determine whether we should activate the timer or deactivate it

    _target_text_source_name = script_state.get_value('text_source')
    with auto_release_source(_target_text_source_name) as _target_source:
        if not _target_source:

            _log(f"Deactivating: target source '{_target_text_source_name}' not found")
            activate(False)
            return

        _target_source_type = obs.obs_source_get_id(_target_source)
        if not _target_source_type.startswith("text"):

            _log(f"Deactivating: target source '{_target_text_source_name}' "
                 f"is no longer a text source (type '{_target_source_type}')")
            activate(False)
            return

        # The target source exists and is a text source; activate according to
        # whether OBS thinks the source is active on any view
        _is_active = obs.obs_source_active(_target_source)
        _log(f"Setting activate({_is_active}): target source '{_target_text_source_name}' ")
        activate(_is_active)

def restart_timer(induce_reset=True):
    """
    Restart the timer given the current script_state settings
    """

    activate(False)

    if induce_reset:
        script_state.clock.reset()

    _source_name = script_state.get_value('text_source')
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
    Applies the given settings into the script_state preferences.

    Called when the user updates any property widget, prior to calling any
    callback registered via obs_property_set_modified_callback.
    """

    _induce_reset = script_state.refresh_preferences(settings)

    _type = script_state.prefs['clock_type'].cur_value

    _is_duration = _type == 'Duration'

    if _is_duration:

        _interval = script_state.prefs['duration'].cur_value
        script_state.clock.set_duration(_interval)

    else:
        _date = script_state.prefs['date'].cur_value
        _time = script_state.prefs['time'].cur_value
        script_state.clock.set_date_time(_date, _time)

    restart_timer(_induce_reset)
    print("script_update complete")

def script_description():
    """
    Returns the Description text to display in the script settings pane.
    (OBS main script callback)
    """
    return blkfmt("""
        Display a countdown clock in an OBS text source.

        Choose whether to count down a given duration,
        or count down to a specified target date and time.
    """)

def script_defaults(settings):
    """
    Set default values for properties
    """

    for _pref_key, _pref in script_state.prefs.items():

        if _pref.type in [script_state.OBS_TEXT, script_state.OBS_COMBO]:

            obs.obs_data_set_default_string(settings, _pref_key, _pref.default)
            _pref.cur_value = obs.obs_data_get_string(settings, _pref_key)

        if _pref.type == script_state.OBS_BOOLEAN:

            obs.obs_data_set_default_bool(settings, _pref_key, _pref.default)
            _pref.cur_value = obs.obs_data_get_bool(settings, _pref_key)

    if script_state.prefs['clock_type'].cur_value == 'Duration':

        script_state.clock.set_duration(
            script_state.prefs['duration'].cur_value)

    else:

        script_state.clock.set_date_time(
            script_state.prefs['date'].cur_value,
            script_state.prefs['time'].cur_value
        )

def global_property_modification_handler(props, prop, settings):
    # TODO factor out the obs_data_get_string vs. bool etc. based on the type
    # of preference in script_state
    _name = obs.obs_property_name(prop)
    print(f"Modified: {_name}: {script_state.get_value(_name)} -> {obs.obs_data_get_string(settings, _name)}")
    set_last_update_timestamp(props, f"Prop {_name} modified")
    return False

def script_properties():
    """
    Create properties for script settings dialog
    """

    _props = obs.obs_properties_create()

    for _pref_key, _pref in script_state.prefs.items():

        _prop = None

        if _pref.type == script_state.OBS_COMBO:

            _prop = obs.obs_properties_add_list(
                _props, _pref_key, _pref.name, _pref.type, obs.OBS_COMBO_FORMAT_STRING)

            if callable(_pref.list_items):

                # _pref.list_items is a function that fills the property list itself
                _fill_prop_list = _pref.list_items
                _fill_prop_list(_props, _prop, "init")
                add_combo_list_regeneration_button(_props, _prop, _fill_prop_list)

            else:

                for _item in _pref.list_items:
                    obs.obs_property_list_add_string(_prop, _item, _item)

        elif _pref.type == script_state.OBS_BOOLEAN:

                _prop = obs.obs_properties_add_bool(_props, _pref_key, _pref.name)
                obs.obs_property_set_enabled(_prop, _pref.default)

        elif _pref.type == script_state.OBS_BUTTON:

            _prop = obs.obs_properties_add_button(_props, _pref_key, _pref.name, _pref.callback)

        elif _pref.type == script_state.OBS_INFO:

            _prop = obs.obs_properties_add_text(_props, _pref_key, _pref.name, obs.OBS_TEXT_INFO)

        else:

            _prop = obs.obs_properties_add_text(_props, _pref_key, _pref.name, _pref.type)

        set_prop_tooltip(_prop, _pref.tooltip)

        if _pref.type != script_state.OBS_BUTTON:
            obs.obs_property_set_modified_callback(_prop, global_property_modification_handler)

    script_state.obs_properties = _props

    set_last_update_timestamp(_props, "script load")
    return _props

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
    def _add_source_handler(signal):
        """Adds a handler that includes the signal name as the first parameter
        to the callback.  The body of the function can't be done inline in the
        for loop below because the lambda would capture a reference to the
        _signal loop variable rather than its contents, so the handler would
        only ever see the last item in the list as its triggering signal name."""
        obs.signal_handler_connect(_sh, signal,
            lambda _cd: handle_source_visibility_signal(signal, _cd))

    for _signal in """
                source_hide
                source_show
                source_rename
                source_create
                source_destroy
            """.split():
        _add_source_handler(_signal)

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
