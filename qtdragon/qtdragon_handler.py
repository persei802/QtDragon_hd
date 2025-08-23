# Copyright (c) 2020 Jim Sloot (persei802@gmail.com)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

import os
import shutil
import datetime
import linuxcnc
from send2trash import send2trash
from connections import Connections
from lib.event_filter import EventFilter
from PyQt5.QtCore import QObject, QEvent, QSize, QRegExp, QTimer, Qt, QUrl
from PyQt5.QtGui import QSyntaxHighlighter, QTextCharFormat, QIntValidator, QRegExpValidator, QFont, QColor, QIcon, QPixmap
from PyQt5.QtWidgets import (QWidget, QCheckBox, QLineEdit, QStyle, QDialog, QInputDialog, QMessageBox,
                             QMenu, QAction, QToolButton)
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from qtvcp.widgets.gcode_editor import GcodeEditor, GcodeEditor as GCODE
from qtvcp.widgets.mdi_history import MDIHistory as MDI_WIDGET
from qtvcp.widgets.tool_offsetview import ToolOffsetView as TOOL_TABLE
from qtvcp.widgets.origin_offsetview import OriginOffsetView as OFFSET_VIEW
from qtvcp.widgets.stylesheeteditor import  StyleSheetEditor as SSE
from qtvcp.widgets.file_manager import FileManager as FM
from qtvcp.lib.keybindings import Keylookup
from qtvcp.core import Status, Action, Info, Path, Tool, Qhal
from qtvcp import logger

LOG = logger.getLogger(__name__)
LOG.setLevel(logger.INFO) # One of DEBUG, INFO, WARNING, ERROR, CRITICAL
KEYBIND = Keylookup()
STATUS = Status()
INFO = Info()
ACTION = Action()
TOOL = Tool()
PATH = Path()
QHAL = Qhal()
HELP = os.path.join(PATH.CONFIGPATH, "help_files")
IMAGES = os.path.join(PATH.HANDLERDIR, 'images')
VERSION = '2.1.8'

# constants for main pages
TAB_MAIN = 0
TAB_FILE = 1
TAB_OFFSETS = 2
TAB_TOOL = 3
TAB_STATUS = 4
TAB_PROBE = 5
TAB_CAMVIEW = 6
TAB_SETTINGS = 7
TAB_UTILS = 8
TAB_ABOUT = 9

# status message alert levels
DEFAULT =  0
WARNING =  1
ERROR = 2
WARNING_COLOR = "yellow"
ERROR_COLOR = "red"

RUN_COLOR = 'green'
PAUSE_COLOR = 'yellow'
STOP_COLOR = 'red'


class Highlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super(Highlighter, self).__init__(document)
        self.highlightingRules = []

        warningLineFormat = QTextCharFormat()
        warningLineFormat.setForeground(QColor(WARNING_COLOR))
        errorLineFormat = QTextCharFormat()
        errorLineFormat.setForeground(QColor(ERROR_COLOR))

        warningLinePattern = QRegExp(".*WARNING.*")
        errorLinePattern = QRegExp(".*ERROR.*")
        self.highlightingRules.append((warningLinePattern, warningLineFormat))
        self.highlightingRules.append((errorLinePattern, errorLineFormat))

    def highlightBlock(self, text):
        for pattern, format in self.highlightingRules:
            expression = QRegExp(pattern)
            index = expression.indexIn(text)
            while index >= 0:
                length = expression.matchedLength()
                self.setFormat(index, length, format)
                index = expression.indexIn(text, index + length)


class MDIPanel(QWidget):
    def __init__(self, parent=None):
        super(MDIPanel, self).__init__()
        self.parent = parent
        self.w = parent.w
        self.mdiLine = self.w.mdihistory.MDILine
                
        # mdi command combobox
        self.mdiLine.setFixedHeight(30)
        self.mdiLine.setPlaceholderText('MDI:')
        self.w.cmb_mdi_texts.addItem("SELECT")
        self.w.cmb_mdi_texts.addItem("HALSHOW")
        self.w.cmb_mdi_texts.addItem("HALMETER")
        self.w.cmb_mdi_texts.addItem("HALSCOPE")
        self.w.cmb_mdi_texts.addItem("STATUS")
        self.w.cmb_mdi_texts.addItem("CLASSICLADDER")
        self.w.cmb_mdi_texts.addItem("CALIBRATION")
        self.w.cmb_mdi_texts.addItem("PREFERENCE")
        self.w.cmb_mdi_texts.addItem("CLEAR HISTORY")
        # signal connections
        self.w.mdi_buttonGroup.buttonClicked.connect(self.handle_keys)
        self.w.btn_mdi_back.pressed.connect(lambda: self.mdiLine.backspace())
        self.w.btn_mdi_enter.pressed.connect(self.mdi_enter_pressed)
        self.w.btn_mdi_clear.pressed.connect(lambda: self.mdiLine.clear())
        self.w.btn_mdi_line_up.pressed.connect(lambda: self.w.mdihistory.line_up())        
        self.w.btn_mdi_line_down.pressed.connect(lambda: self.w.mdihistory.line_down())        
        self.w.btn_mdi_left.pressed.connect(lambda: self.mdiLine.cursorBackward(False))
        self.w.btn_mdi_right.pressed.connect(lambda: self.mdiLine.cursorForward(False))
        self.w.cmb_mdi_texts.activated.connect(self.mdi_select_text)

    def handle_keys(self, button):
        if button == self.w.btn_mdi_space:
            char = ' '
        elif button == self.w.btn_mdi_dot:
            char = '.'
        elif button == self.w.btn_mdi_minus:
            char = '-'
        else:
            char = button.text()
        self.mdiLine.insert(char)
        self.mdiLine.setFocus()

    def mdi_enter_pressed(self):
        if self.mdiLine.text() == "CLEAR HISTORY":
            self.parent.add_status("MDI history cleared")
        self.w.mdihistory.run_command()
        self.mdiLine.clear()

    def mdi_select_text(self):
        if self.w.cmb_mdi_texts.currentIndex() <= 0: return
        self.mdiLine.setText(self.w.cmb_mdi_texts.currentText())
        self.w.cmb_mdi_texts.setCurrentIndex(0)

# this class provides an overloaded function to disable navigation links
class WebPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, navtype, mainframe):
        if navtype == self.NavigationTypeLinkClicked: return False
        return super().acceptNavigationRequest(url, navtype, mainframe)


class Gcode_Editor(GcodeEditor):
    def __init__(self, parent):
        super(Gcode_Editor, self).__init__()
        self.parent = parent
        self.w = self.parent.w
        self.active_file = None
        self.editor.setCaretForegroundColor(Qt.yellow)
        # instance patch the GcodeEditor actions
        try:
            self.newAction.triggered.disconnect()
            self.openAction.triggered.disconnect()
            self.saveAction.triggered.disconnect()
            self.exitAction.triggered.disconnect()
        except TypeError:
            pass
        self.newAction.triggered.connect(self.newCall)
        self.openAction.triggered.connect(lambda: self.openCall(fname=None))
        self.saveAction.triggered.connect(lambda: self.saveCall(fname=None))
        self.exitAction.triggered.connect(self.exitCall)
        # permanently set to editing mode
        self.editMode()

    def newCall(self):
        self.active_file = None
        self.new()

    def openCall(self, fname=None):
        if self.editor.isModified():
            result = self.killCheck()
            if not result: return
        if fname is None:
            self.getFileName()
        else:
            self.active_file = fname
            self.editor.load_text(fname)
            self.label.setText(f'  Editing {fname}')
            self.parent.add_status(f"Opened gcode file {fname}")

    def saveCall(self, fname=None):
        if self.active_file is None:
            self.getSaveFileName()
        else:
            saved = ACTION.SAVE_PROGRAM(self.editor.text(), self.active_file)
            if saved is not None:
                self.editor.setModified(False)
                self.parent.add_status(f"Saved gcode file {self.active_file}")
            
    def exitCall(self):
        if self.editor.isModified():
            result = self.killCheck()
            if not result: return
        self.w.stackedWidget_file.setCurrentIndex(0)

    def openReturn(self, fname):
        self.openCall(fname)
        self.editor.setModified(False)

    def saveReturn(self, fname):
        self.active_file = fname
        saved = ACTION.SAVE_PROGRAM(self.editor.text(), fname)
        if saved is not None:
            self.editor.setModified(False)

class HandlerClass:
    def __init__(self, halcomp, widgets, paths):
        self.h = halcomp
        self.w = widgets
        self.styleeditor = SSE(widgets, paths, addBuiltinStyles=False)
        self.settings_checkboxes = []
        self.touchoff_checkboxes = []
        self.settings_touchoff = []
        self.settings_offsets = []
        self.settings_spindle = []
        KEYBIND.add_call('Key_F4', 'on_keycall_F4')
        KEYBIND.add_call('Key_F12','on_keycall_F12')
        KEYBIND.add_call('Key_Pause', 'on_keycall_PAUSE')
        KEYBIND.add_call('Key_Any', 'on_keycall_PAUSE')
        KEYBIND.add_call('Key_Space', 'on_keycall_PAUSE')
        # references to utility objects to be initialized
        self.probe = None
        self.tool_db = None
        self.zlevel = None
        self.mdiPanel = None
        # some global variables
        self.dialog_code = 'CALCULATOR'
        self.kbd_code = 'KEYBOARD'
        self.tool_code = 'TOOLCHOOSER'
        self.filemanager = None
        self.deleteFile = None
        self.current_tool = 0
        self.tool_list = []
        self.next_available = 0
        self.start_line = 0
        self.feedrate_style = ''
        self.statusbar_style = ''
        self.stat_warnings = 0
        self.stat_errors = 0
        self.spindle_role = 'power'
        self.tmpl = '.3f' if INFO.MACHINE_IS_METRIC else '.4f'
        self.machine_units = "MM" if INFO.MACHINE_IS_METRIC else "IN"
        self.min_spindle_rpm = int(INFO.MIN_SPINDLE_SPEED)
        self.max_spindle_rpm = int(INFO.MAX_SPINDLE_SPEED)
        self.max_linear_velocity = int(INFO.MAX_LINEAR_JOG_VEL)
        self.default_linear_jog_vel = int(INFO.DEFAULT_LINEAR_JOG_VEL)
        self.max_angular_velocity = int(INFO.MAX_ANGULAR_JOG_VEL)
        self.default_angular_jog_vel = int(INFO.DEFAULT_ANGULAR_JOG_VEL)
        self.progress = 0
        self.axis_list = INFO.AVAILABLE_AXES
        self.jog_from_name = INFO.GET_JOG_FROM_NAME
        self.system_list = ["G54","G55","G56","G57","G58","G59","G59.1","G59.2","G59.3"]
        self.slow_linear_jog = False
        self.slow_angular_jog = False
        self.slow_jog_factor = 10
        self.reload_tool = 0
        self.last_loaded_program = ""
        self.current_loaded_program = None
        self.first_turnon = True
        self.macros_defined = list()
        self.pause_timer = QTimer()
        self.source_file = ''
        self.destination_file = ''
        self.icon_btns = {'exit'       : 'SP_BrowserStop',
                          'cycle_start': 'SP_MediaPlay',
                          'reload'     : 'SP_BrowserReload',
                          'step'       : 'SP_ArrowForward',
                          'pause'      : 'SP_MediaPause',
                          'stop'       : 'SP_MediaStop'}

        self.adj_list = ['maxvel_ovr', 'rapid_ovr', 'feed_ovr', 'spindle_ovr']

        self.unit_label_list = ["zoffset_units", "retract_units", "zsafe_units", "touch_units", "max_probe_units",
                                "start_height_units", "sensor_units", "gauge_units", "rotary_units", "mpg_units"]

        self.unit_speed_list = ["search_vel_units", "probe_vel_units"]

        self.lineedit_list = ["work_height", "touch_height", "sensor_height", "laser_x", "laser_y", "camera_x", "camera_y",
                              "search_vel", "probe_vel", "retract", "max_probe", "start_height", "eoffset", "sensor_x", "sensor_y",
                              "zsafe", "probe_x", "probe_y", "rotary_height", "gauge_height", "spindle_raise"]

        self.axis_a_list = ["dro_axis_a", "lbl_max_angular", "lbl_max_angular_vel", "angular_increment",
                            "action_zero_a", "btn_rewind_a", "action_home_a", "widget_angular_jog"]

        self.gcode_titles = ["GCODE", "MDI INPUT"]

        STATUS.connect('general', self.dialog_return)
        STATUS.connect('state-estop', lambda w: self.add_status("ESTOP activated", ERROR))
        STATUS.connect('state-estop-reset', lambda w: self.add_status("ESTOP reset"))
        STATUS.connect('state-on', lambda w: self.enable_onoff(True))
        STATUS.connect('state-off', lambda w: self.enable_onoff(False))
        STATUS.connect('mode-manual', lambda w: self.enable_auto(False))
        STATUS.connect('mode-mdi', lambda w: self.enable_auto(False))
        STATUS.connect('mode-auto', lambda w: self.enable_auto(True))
        STATUS.connect('gcode-line-selected', lambda w, line: self.set_start_line(line))
        STATUS.connect('hard-limits-tripped', self.hard_limit_tripped)
        STATUS.connect('user-system-changed', lambda w, data: self.user_system_changed(data))
        STATUS.connect('metric-mode-changed', lambda w, mode: self.metric_mode_changed(mode))
        STATUS.connect('tool-in-spindle-changed', lambda w, tool: self.tool_changed(tool))
        STATUS.connect('file-loaded', lambda w, filename: self.file_loaded(filename))
        STATUS.connect('all-homed', self.all_homed)
        STATUS.connect('not-all-homed', self.not_all_homed)
        STATUS.connect('program_pause_changed', lambda w, state: self.pause_changed(state))
        STATUS.connect('interp-idle', lambda w: self.stop_timer())
        STATUS.connect('graphics-gcode-properties', lambda w, d: self.update_gcode_properties(d))
        STATUS.connect('status-message', lambda w, d, o: self.add_external_status(d, o)) 
        STATUS.connect('override-limits-changed', lambda w, state, data: self._check_override_limits(state, data))

    def class_patch__(self):
        pass
#        self.old_fman = FM.load
#        FM.load = self.load_code

    def initialized__(self):
        self.init_pins()
        self.init_preferences()
        self.init_tooldb()
        self.init_widgets()
        self.init_gcode_editor()
        self.init_file_manager()
        self.init_probe()
        self.init_mdi_panel()
        self.init_macros()
        self.init_utils()
        self.init_about()
        self.init_adjustments()
        self.init_event_filter()
        # initialize widget states
        self.w.stackedWidget_gcode.setCurrentIndex(0)
        self.w.btn_dimensions.setChecked(True)
        self.w.page_buttonGroup.buttonClicked.connect(self.main_tab_changed)
        self.w.preset_buttonGroup.buttonClicked.connect(self.preset_jograte)
        self.use_mpg_changed(self.w.chk_use_mpg.isChecked())
        self.use_camera_changed(self.w.chk_use_camera.isChecked())
        self.chk_use_basic_calc(self.w.chk_use_basic_calculator.isChecked())
        self.touchoff_changed(True)
        # determine if A axis widgets should be visible or not
        if not "A" in self.axis_list:
            for item in self.axis_a_list:
                self.w[item].hide()
            self.w.axis_a_height.hide()
        # set validators for lineEdit widgets
        if INFO.MACHINE_IS_METRIC:
            regex = QRegExp(r'^((\d{1,4}(\.\d{1,3})?)|(\.\d{1,3}))$')
        else:
            regex = QRegExp(r'^((\d{1,3}(\.\d{1,4})?)|(\.\d{1,4}))$')
        valid = QRegExpValidator(regex)
        for val in self.lineedit_list:
            self.w['lineEdit_' + val].setValidator(valid)
        self.w.lineEdit_spindle_raise.setValidator(QIntValidator(0, 99))
        self.w.lineEdit_max_power.setValidator(QIntValidator(0, 9999))
        self.w.lineEdit_max_volts.setValidator(QIntValidator(0, 999))
        self.w.lineEdit_max_amps.setValidator(QIntValidator(0, 99))
        self.w.lineEdit_tool_in_spindle.setValidator(QIntValidator(0, 99999))
        # set unit labels according to machine mode
        self.w.lbl_machine_units.setText("METRIC" if INFO.MACHINE_IS_METRIC else "IMPERIAL")
        for i in self.unit_label_list:
            self.w['lbl_' + i].setText(self.machine_units)
        for i in self.unit_speed_list:
            self.w['lbl_' + i].setText(self.machine_units + "/MIN")
        self.w.setWindowFlags(Qt.FramelessWindowHint)
        # instantiate color highlighter for machine log
        self.highlighter = Highlighter(self.w.machine_log.logText)

        # connect all signals to corresponding slots
        connect = Connections(self, self.w)
        self.w.tooloffsetview.tablemodel.layoutChanged.connect(self.get_checked_tools)
        self.w.tooloffsetview.tablemodel.dataChanged.connect(lambda new, old, roles: self.tool_data_changed(new, old, roles))
        self.w.statusbar.messageChanged.connect(self.statusbar_changed)
        self.w.stackedWidget_gcode.currentChanged.connect(self.gcode_widget_changed)
        self.w.lineEdit_tool_in_spindle.returnPressed.connect(self.tool_edit_finished)
        self.w.spindle_power.role_changed.connect(self.spindle_role_changed)

    #############################
    # SPECIAL FUNCTIONS SECTION #
    #############################

    def init_pins(self):
        # spindle control pins
        pin = QHAL.newpin("spindle-amps", Qhal.HAL_FLOAT, Qhal.HAL_IN)
        pin.value_changed.connect(self.spindle_pwr_changed)
        pin = QHAL.newpin("spindle-volts", Qhal.HAL_FLOAT, Qhal.HAL_IN)
        pin.value_changed.connect(self.spindle_pwr_changed)
        pin = QHAL.newpin("modbus-fault", Qhal.HAL_U32, Qhal.HAL_IN)
        pin.value_changed.connect(lambda data: self.w.lbl_modbus_fault.setText(hex(data)))
        pin = QHAL.newpin("modbus-errors", Qhal.HAL_U32, Qhal.HAL_IN)
        pin.value_changed.connect(lambda data: self.w.lbl_modbus_errors.setText(str(data)))
        QHAL.newpin("spindle-inhibit", Qhal.HAL_BIT, Qhal.HAL_OUT)
        # external offset control pins
        QHAL.newpin("eoffset-count", Qhal.HAL_S32, Qhal.HAL_OUT)
        pin = QHAL.newpin("eoffset-value", Qhal.HAL_FLOAT, Qhal.HAL_IN)
        pin.value_changed.connect(self.eoffset_value_changed)
        pin = QHAL.newpin("map-ready", Qhal.HAL_BIT, Qhal.HAL_IN)
        pin.value_changed.connect(self.map_ready_changed)
        QHAL.newpin("comp-on", Qhal.HAL_BIT, Qhal.HAL_OUT)
        # MPG axis select pins
        pin = QHAL.newpin("axis-select-x", Qhal.HAL_BIT, Qhal.HAL_IN)
        pin.value_changed.connect(self.show_selected_axis)
        pin = QHAL.newpin("axis-select-y", Qhal.HAL_BIT, Qhal.HAL_IN)
        pin.value_changed.connect(self.show_selected_axis)
        pin = QHAL.newpin("axis-select-z", Qhal.HAL_BIT, Qhal.HAL_IN)
        pin.value_changed.connect(self.show_selected_axis)
        pin = QHAL.newpin("axis-select-a", Qhal.HAL_BIT, Qhal.HAL_IN)
        pin.value_changed.connect(self.show_selected_axis)
        # MPG encoder disable
        QHAL.newpin("mpg-disable", Qhal.HAL_BIT, Qhal.HAL_OUT)
        # MPG increment
        pin = QHAL.newpin("mpg_increment", Qhal.HAL_FLOAT, Qhal.HAL_IN)
        pin.value_changed.connect(lambda data: self.w.lineEdit_mpg_increment.setText(str(data * 4)))
        # program runtimer
        pin = QHAL.newpin("runtime-start", Qhal.HAL_BIT, Qhal.HAL_OUT)   
        pin = QHAL.newpin("runtime-pause", Qhal.HAL_BIT, Qhal.HAL_OUT)
        pin = QHAL.newpin("runtime-seconds", Qhal.HAL_U32, Qhal.HAL_IN)
        pin.value_changed.connect(self.update_runtime)
        pin = QHAL.newpin("runtime-minutes", Qhal.HAL_U32, Qhal.HAL_IN)
        pin = QHAL.newpin("runtime-hours", Qhal.HAL_U32, Qhal.HAL_IN)

        self.h['runtime-start'] = False
        self.h['runtime-pause'] = False

    def init_preferences(self):
        if not self.w.PREFS_:
            self.add_status("No preference file found, enable preferences in screenoptions widget", ERROR)
            return
        # using this method allows adding or removing objects in the UI without modifying the handler
        # operational checkboxes
        self.settings_checkboxes = self.w.groupBox_operational.findChildren(QCheckBox)
        for checkbox in self.settings_checkboxes:
            checkbox.setChecked(self.w.PREFS_.getpref(checkbox.objectName(), False, bool, 'CUSTOM_FORM_ENTRIES'))
        # touchoff checkboxes
        self.touchoff_checkboxes = self.w.frame_touchoff.findChildren(QCheckBox)
        for checkbox in self.touchoff_checkboxes:
            checkbox.setChecked(self.w.PREFS_.getpref(checkbox.objectName(), False, bool, 'CUSTOM_FORM_ENTRIES'))
        # touchoff settings
        self.settings_touchoff = self.w.frame_touchoff.findChildren(QLineEdit)
        for touchoff in self.settings_touchoff:
            touchoff.setText(self.w.PREFS_.getpref(touchoff.objectName(), '10', str, 'CUSTOM_FORM_ENTRIES'))
        # offsets settings
        self.settings_offsets = self.w.frame_locations.findChildren(QLineEdit)
        for offset in self.settings_offsets:
            offset.setText(self.w.PREFS_.getpref(offset.objectName(), '10', str, 'CUSTOM_FORM_ENTRIES'))
        # spindle settings
        self.settings_spindle = self.w.frame_spindle_settings.findChildren(QLineEdit)
        for spindle in self.settings_spindle:
            spindle.setText(self.w.PREFS_.getpref(spindle.objectName(), '10', str, 'CUSTOM_FORM_ENTRIES'))
        self.max_spindle_power = int(self.w.lineEdit_max_power.text())
        self.max_spindle_volts = int(self.w.lineEdit_max_volts.text())
        self.max_spindle_amps = int(self.w.lineEdit_max_amps.text())
        # all remaining fields
        self.last_loaded_program = self.w.PREFS_.getpref('last_loaded_file', None, str,'BOOK_KEEPING')
        self.reload_tool = self.w.PREFS_.getpref('Tool to load', 0, int,'CUSTOM_FORM_ENTRIES')
        self.w.lineEdit_work_height.setText(self.w.PREFS_.getpref('Work Height', '20', str, 'CUSTOM_FORM_ENTRIES'))
        
    def closing_cleanup__(self):
        if not self.w.PREFS_: return
        for checkbox in self.settings_checkboxes:
            self.w.PREFS_.putpref(checkbox.objectName(), checkbox.isChecked(), bool, 'CUSTOM_FORM_ENTRIES')
        for checkbox in self.touchoff_checkboxes:
            self.w.PREFS_.putpref(checkbox.objectName(), checkbox.isChecked(), bool, 'CUSTOM_FORM_ENTRIES')
        for touchoff in self.settings_touchoff:
            self.w.PREFS_.putpref(touchoff.objectName(), touchoff.text(), str, 'CUSTOM_FORM_ENTRIES')
        for offset in self.settings_offsets:
            self.w.PREFS_.putpref(offset.objectName(), offset.text(), str, 'CUSTOM_FORM_ENTRIES')
        for spindle in self.settings_spindle:
            self.w.PREFS_.putpref(spindle.objectName(), spindle.text(), str, 'CUSTOM_FORM_ENTRIES')
        if self.last_loaded_program is not None:
            self.w.PREFS_.putpref('last_loaded_directory', os.path.dirname(self.last_loaded_program), str, 'BOOK_KEEPING')
            self.w.PREFS_.putpref('last_loaded_file', self.last_loaded_program, str, 'BOOK_KEEPING')
        self.w.PREFS_.putpref('Tool to load', STATUS.get_current_tool(), int, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Work Height', self.w.lineEdit_work_height.text(), float, 'CUSTOM_FORM_ENTRIES')

        # check for closing cleanup methods in imported utilities
        self.setup_utils.closing_cleanup__()

    def init_widgets(self):
        self.w.main_tab_widget.setCurrentIndex(TAB_MAIN)
        self.w.adj_linear_jog.setValue(self.default_linear_jog_vel)
        self.w.adj_linear_jog.setMaximum(self.max_linear_velocity)
        self.w.adj_angular_jog.setValue(self.default_angular_jog_vel)
        self.w.adj_angular_jog.setMaximum(self.max_angular_velocity)
        self.w.adj_spindle_ovr.setValue(100)
        self.w.chk_override_limits.setChecked(False)
        self.w.chk_override_limits.setEnabled(False)
        self.w.lbl_home_x.setText(INFO.get_error_safe_setting('JOINT_0', 'HOME',"50"))
        self.w.lbl_home_y.setText(INFO.get_error_safe_setting('JOINT_1', 'HOME',"50"))
        self.w.lbl_max_velocity.setText(f"{self.max_linear_velocity}")
        self.w.lbl_max_angular.setText(f"{self.max_angular_velocity}")
        self.w.lineEdit_min_rpm.setText(f"{self.min_spindle_rpm}")
        self.w.lineEdit_max_rpm.setText(f"{self.max_spindle_rpm}")
        self.w.lbl_pgm_color.setStyleSheet(f'Background-color: {STOP_COLOR};')
        # gcode file history
        self.w.cmb_gcode_history.addItem("No File Loaded")
        self.w.cmb_gcode_history.view().setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # gcode editor mode
        self.w.gcode_viewer.readOnlyMode()
        # set calculator mode for menu buttons
        for i in ("x", "y", "z"):
            self.w["axistoolbutton_" + i].set_dialog_code('CALCULATOR')
        # disable mouse wheel events on comboboxes
        self.w.cmb_gcode_history.wheelEvent = lambda event: None
        self.w.cmb_icon_select.wheelEvent = lambda event: None
        self.w.jogincrements_linear.wheelEvent = lambda event: None
        self.w.jogincrements_angular.wheelEvent = lambda event: None
        # turn off table grids
        self.w.offset_table.setShowGrid(False)
        self.w.tooloffsetview.setShowGrid(False)
        # move clock to statusbar
        self.w.lbl_clock.set_textTemplate(f'QtDragon {VERSION}  <>  %I:%M:%S %p')
        self.w.statusbar.addPermanentWidget(self.w.lbl_clock)
        # set homing buttons to correct joints
        self.w.action_home_x.set_joint(self.jog_from_name['X'])
        self.w.action_home_y.set_joint(self.jog_from_name['Y'])
        self.w.action_home_z.set_joint(self.jog_from_name['Z'])
        # set Zero reference buttons to correct joints
        self.w.action_zero_x.set_joint(self.jog_from_name['X'])
        self.w.action_zero_y.set_joint(self.jog_from_name['Y'])
        self.w.action_zero_z.set_joint(self.jog_from_name['Z'])
        # set axis reference buttons to correct joints
        self.w.axistoolbutton_x.set_joint(self.jog_from_name['X'])
        self.w.axistoolbutton_y.set_joint(self.jog_from_name['Y'])
        self.w.axistoolbutton_z.set_joint(self.jog_from_name['Z'])
        if 'A' in self.axis_list:
            self.w.action_home_a.set_joint(self.jog_from_name['A'])
        # initialize spindle gauge
        self.w.gauge_spindle._value_font_size = 12
        self.w.gauge_spindle.set_threshold(self.min_spindle_rpm)
        # initialize jog joypads
        self.w.jog_xy.setFont(QFont('Lato Heavy', 9))
        self.w.jog_az.setFont(QFont('Lato Heavy', 9))
        self.w.jog_xy.set_tooltip('C', 'Toggle FAST / SLOW linear jograte')
        self.w.jog_az.set_tooltip('C', 'Toggle FAST / SLOW angular jograte')
        # apply standard button icons
        for btn in self.icon_btns:
            style = self.w[f'btn_{btn}'].style()
            icon = style.standardIcon(getattr(QStyle, self.icon_btns[btn]))
            self.w[f'btn_{btn}'].setIcon(icon)
        # populate tool icon combobox
        path = os.path.join(PATH.CONFIGPATH, "tool_icons")
        self.w.cmb_icon_select.addItem('SELECT ICON')
        if os.path.isdir(path):
            icons = os.listdir(path)
            icons.sort()
            for item in icons:
                if item.endswith(".png"):
                    self.w.cmb_icon_select.addItem(item)
        else:
            LOG.info(f"No tool icons found in {path}")
        self.w.cmb_icon_select.addItem("undefined")
        # spindle pause delay timer
        self.pause_timer.setSingleShot(True)
        self.pause_timer.timeout.connect(self.spindle_pause_timer)
        # default styles for feedrate and statusbar
        self.feedrate_style = self.w.lbl_feedrate.styleSheet()
        self.statusbar_style = self.w.statusbar.styleSheet()

    def init_gcode_editor(self):
        self.gcode_editor = Gcode_Editor(self)
        self.w.layout_gcode_editor.addWidget(self.gcode_editor)

    def init_file_manager(self):
        self.w.filemanager_media.table.setShowGrid(False)
        self.w.filemanager_media.chk_restricted.setChecked(True)
        self.w.filemanager_media.onMediaClicked()
        self.w.filemanager_media.loadButton.hide()
        self.w.filemanager_media.copy_control.hide()
        self.w.filemanager_user.table.setShowGrid(False)
        self.w.filemanager_user.chk_restricted.setChecked(True)
        self.w.filemanager_user.onUserClicked()
        self.w.filemanager_user.loadButton.hide()
        self.w.filemanager_user.copy_control.hide()
        self.w.filemanager_user.table.clicked.connect(lambda index: self.select_filemanager(True))
        self.w.filemanager_media.table.clicked.connect(lambda index: self.select_filemanager(False))
        # set initial active file manager
        self.filemanager = self.w.filemanager_user
        # create the input dialog for non keyboard input
        self.input_dialog = QInputDialog()
        self.input_dialog.setModal(False)
        self.input_dialog.setWindowModality(Qt.NonModal)
        self.input_dialog.accepted.connect(self.on_input_accepted)
        # create message box for file control buttons
        self.messagebox = QMessageBox()
        self.messagebox.setWindowModality(Qt.NonModal)
        self.messagebox.setStandardButtons(QMessageBox.No | QMessageBox.Yes)
        self.messagebox.buttonClicked.connect(self.do_file_copy)

    def init_tooldb(self):
        from lib.tool_db import Tool_Database
        self.tool_db = Tool_Database(self.w, self)
        self.db_helpfile = os.path.join(HELP, 'tooldb_help.html')
        self.tool_db.hal_init()

    def init_probe(self):
        probe = INFO.get_error_safe_setting('PROBE', 'USE_PROBE', 'none').lower()
        if probe == 'versaprobe':
            LOG.info("Using Versa Probe")
            from qtvcp.widgets.versa_probe import VersaProbe
#            from lib.versa_probe import VersaProbe
            self.probe = VersaProbe()
            self.probe.setObjectName('versaprobe')
            self.w.btn_probe.setProperty('title', 'VERSA PROBE')
        elif probe == 'basicprobe':
            LOG.info("Using Basic Probe")
            from lib.basic_probe import BasicProbe
            self.probe = BasicProbe(self)
            self.probe.setObjectName('basicprobe')
            self.w.btn_probe.setProperty('title', 'BASIC PROBE')
        else:
            LOG.info("No valid probe widget specified")
            self.w.btn_probe.hide()
            self.w.chk_use_basic_calculator.hide()
            self.w.chk_inhibit_spindle.hide()
            self.w.probe_offset.hide()
            return
        self.w.probe_layout.addWidget(self.probe)
        self.probe.hal_init()

    def init_mdi_panel(self):
        self.mdiPanel = MDIPanel(self)
        self.w.mdi_keyboard.setVisible(self.w.chk_use_mdi_keyboard.isChecked())
        
    def init_utils(self):
        from lib.setup_utils import Setup_Utils
        self.setup_utils = Setup_Utils(self.w, self)
        self.setup_utils.init_utils()
        self.util_list = self.setup_utils.get_util_list()
        # designer doesn't allow adding buttons not derived from QAbstractButton class
        self.w.page_buttonGroup.addButton(self.w.btn_utils)
        menu = QMenu(self.w.btn_utils)
        for util in self.util_list:
            action = QAction(util, self.w.btn_utils)
            action.triggered.connect(lambda checked, t=util: self.update_utils_button(t))
            menu.addAction(action)
        self.w.btn_utils.setMenu(menu)
        # if z level compensation wasn't installed, disable the button
        if self.zlevel is None:
            self.w.btn_enable_comp.setEnabled(False)
        self.get_next_available()
        self.tool_db.update_tools(self.tool_list)

    def init_about(self):
        self.about_dict = {'vfd'          : 'USING A VFD',
                           'spindle_pause': 'SPINDLE PAUSE',
                           'mpg'          : 'USING A MPG',
                           'touchoff'     : 'TOOL TOUCHOFF',
                           'runfromline'  : 'RUN FROM LINE',
                           'stylesheets'  : 'STYLESHEETS',
                           'rotary_axis'  : 'ROTARY AXIS',
                           'custom'       : 'CUSTOM PANELS'}
        self.w.page_buttonGroup.addButton(self.w.btn_about)
        menu = QMenu(self.w.btn_about)
        for key, val in self.about_dict.items():
            action =  QAction(val, self.w.btn_about)
            action.triggered.connect(lambda checked, t=key: self.update_about_button(t))
            menu.addAction(action)
        self.w.btn_about.setMenu(menu)
        self.web_view_about = QWebEngineView()
        self.web_page_about = WebPage()
        self.web_view_about.setPage(self.web_page_about)
        self.w.layout_about_pages.addWidget(self.web_view_about)

    def init_event_filter(self):
        self.default_line_style = self.w.lineEdit_work_height.styleSheet()
        line_list = self.lineedit_list
        # eoffset is removed because it's readonly
        if 'eoffset' in line_list:
            line_list.remove('eoffset')
        self.event_filter = EventFilter(self.w)
        for line in line_list:
            self.w[f'lineEdit_{line}'].installEventFilter(self.event_filter)
        self.w.lineEdit_tool_in_spindle.installEventFilter(self.event_filter)
        self.event_filter.set_line_list(line_list)
        self.event_filter.set_tool_list('tool_in_spindle')
        self.event_filter.set_parms(('_handler_', False))
        self.event_filter.set_dialog_mode(self.w.chk_use_handler_calculator.isChecked())

    def init_macros(self):
        # macro buttons defined in INI under [MDI_COMMAND_LIST]
        for i in range(20):
            button = self.w[f'btn_macro{i}']
            key = button.property('ini_mdi_key')
            if key == '' or INFO.get_ini_mdi_command(key) is None:
                # fallback to legacy nth line
                key = button.property('ini_mdi_number')
            try:
                code = INFO.get_ini_mdi_command(key)
                if code is None: raise Exception
                self.macros_defined.append(i)
            except:
                button.setText('')
                button.setEnabled(False)
        self.w.group1_macro_buttons.hide()
        self.w.group2_macro_buttons.hide()
        self.show_macros_clicked(self.w.btn_show_macros.isChecked())

    def init_adjustments(self):
        # modify the status adjustment bars to have custom icons
        icon = QIcon(os.path.join(IMAGES, 'arrow_left.png'))
        icon_size = 24
        for item in self.adj_list:
            btn = self.w[f"adj_{item}"].tb_down
            btn.setArrowType(Qt.NoArrow)
            btn.setIcon(icon)
            btn.setIconSize(QSize(icon_size, icon_size))
        icon = QIcon(os.path.join(IMAGES, 'arrow_right.png'))
        for item in self.adj_list:
            btn = self.w[f"adj_{item}"].tb_up
            btn.setArrowType(Qt.NoArrow)
            btn.setIcon(icon)
            btn.setIconSize(QSize(icon_size, icon_size))
        # slow the adjustment bars timer down
        for item in self.adj_list:
            self.w[f"adj_{item}"].timer_value = 200

    def processed_key_event__(self, receiver, event, is_pressed, key, code, shift, cntrl):
        # when typing in MDI, we don't want keybinding to call functions
        # so we catch and process the events directly.
        # We do want ESC, F1 and F2 to call keybinding functions though
        if code not in(Qt.Key_Escape, Qt.Key_F1 , Qt.Key_F2):
#                    Qt.Key_F3, Qt.Key_F4, Qt.Key_F5):

            # search for the top widget of whatever widget received the event
            # then check if it's one we want the keypress events to go to
            flag = False
            receiver2 = receiver
            while receiver2 is not None and not flag:
                if isinstance(receiver2, QDialog):
                    flag = True
                    break
                if isinstance(receiver2, QLineEdit):
                    flag = True
                    break
                if isinstance(receiver2, MDI_WIDGET):
                    flag = True
                    break
                if isinstance(receiver2, GCODE):
                    flag = True
                    break
                if isinstance(receiver2, TOOL_TABLE):
                    flag = True
                    break
                if isinstance(receiver2, OFFSET_VIEW):
                    flag = True
                    break
                receiver2 = receiver2.parent()

            if flag:
                if isinstance(receiver2, GCODE):
                    # if in manual do our keybindings - otherwise
                    # send events to gcode widget
                    if STATUS.is_man_mode() == False or not receiver2.isReadOnly():
                        if is_pressed:
                            receiver.keyPressEvent(event)
                            event.accept()
                        return True
                if is_pressed:
                    receiver.keyPressEvent(event)
                    event.accept()
                    return True
                else:
                    event.accept()
                    return True

        if event.isAutoRepeat(): return True
        # ok if we got here then try keybindings
        return KEYBIND.manage_function_calls(self, event, is_pressed, key, shift, cntrl)

    #########################
    # CALLBACKS FROM STATUS #
    #########################

    def dialog_return(self, w, message):
        rtn = message.get('RETURN')
        name = message.get('NAME')
        obj = message.get('OBJECT')
        unhome_code = bool(message.get('ID') == '_unhome_')
        lower_code = bool(message.get('ID') == '_wait_to_lower_')
        handler_code = bool(message.get('ID') == '_handler_')
        delete_code = bool(message.get('ID') == '_delete_')
        save_gcode_code = bool(message.get('ID') == '_save_gcode_')
        if unhome_code and name == 'MESSAGE' and rtn is True:
            ACTION.SET_MACHINE_UNHOMED(-1)
            self.add_status("All axes unhomed")
        elif lower_code and name == 'MESSAGE':
            self.h['spindle-inhibit'] = False
            # add time delay for spindle to attain speed
            self.pause_timer.start(1000)
        elif delete_code and name == 'MESSAGE':
            if rtn is True:
                send2trash(self.deleteFile)
                self.filemanager.textLine.clear()
                self.add_status(f"{self.deleteFile} sent to Trash")
            else:
                self.add_status(f"{self.deleteFile} not deleted")
        elif save_gcode_code and name == 'SAVE':
            if rtn is None: return
            saved = ACTION.SAVE_PROGRAM(self.w.gcodeeditor.editor.text(), rtn)
            if saved is not None:
                self.w.gcodeeditor.editor.setModified(False)
        elif handler_code and name == self.dialog_code:
            obj.setStyleSheet(self.default_line_style)
            if rtn is None: return
            LOG.debug(f'message return: {message}')
            if obj == self.w.lineEdit_spindle_raise:
                obj.setText(str(int(rtn)))
            else:
                obj.setText(f'{rtn:{self.tmpl}}')
        elif handler_code and name == self.kbd_code:
            obj.setStyleSheet(self.default_line_style)
            if rtn is None: return
            LOG.debug(f'message return: {message}')
            obj.setText(rtn)
        elif handler_code and name == self.tool_code:
            if rtn is None: return
            self.w.lineEdit_tool_in_spindle.setText(str(rtn))
            self.tool_edit_finished()

    def tool_edit_finished(self):
        tool = int(self.w.lineEdit_tool_in_spindle.text())
        if tool == self.current_tool:
            self.add_status(f"Tool {tool} already in spindle", WARNING)
        elif tool not in self.tool_list:
            self.add_status(f'Tool {tool} is not a valid tool', WARNING)
            self.w.lineEdit_tool_in_spindle.setText(str(self.current_tool))
        else:
            self.current_tool = tool
            ACTION.CALL_MDI_WAIT(f'M61 Q{tool}', mode_return=True)
        self.w.lineEdit_tool_in_spindle.clearFocus()

    def spindle_role_changed(self, role):
        self.spindle_role = role
        if role == 'power':
            self.w.spindle_power.setMaximum(self.max_spindle_power)
            self.w.spindle_power.setFormat("POWER %p%")
        elif role == 'volts':
            self.w.spindle_power.setMaximum(self.max_spindle_volts)
        elif role == 'amps':
            self.w.spindle_power.setMaximum(self.max_spindle_amps)
        self.spindle_pwr_changed()

    def spindle_pwr_changed(self):
        if self.spindle_role == 'power':
            # V x I x PF x sqrt(3)
            # this calculation assumes a power factor of 0.8
            power = int(self.h['spindle-volts'] * self.h['spindle-amps'] * 1.386)
            if power > self.max_spindle_power:
                self.w.spindle_power.setFormat('OUT OF RANGE')
                self.w.spindle_power.setValue(0)
            else:
                self.w.spindle_power.setValue(power)
        elif self.spindle_role == 'volts':
            volts = self.h['spindle-volts']
            if volts > self.max_spindle_volts:
                print('Volts out of range')
                self.w.spindle_power.setFormat('OUT OF RANGE')
                self.w.spindle_power.setValue(0)
            else:
                self.w.spindle_power.setFormat(f'{volts:.1f} VOLTS')
                self.w.spindle_power.setValue(int(volts))
        elif self.spindle_role == 'amps':
            amps = self.h['spindle-amps']
            if amps > self.max_spindle_amps:
                self.w.spindle_power.setFormat('OUT OF RANGE')
                self.w.spindle_power.setValue(0)
            else:
                self.w.spindle_power.setFormat(f'{amps:.1f} AMPS')
                self.w.spindle_power.setValue(int(amps))

    def eoffset_value_changed(self, data):
        if not self.w.btn_pause_spindle.isChecked() and not self.w.btn_enable_comp.isChecked():
            self.w.lineEdit_eoffset.setText("DISABLED")
        else:
            self.w.lineEdit_eoffset.setText(f"{data:.3f}")

    def map_ready_changed(self, state):
        if state:
            try:
                self.zlevel.map_ready()
            except Exception as e:
                self.add_status(f"Map ready - {e}", WARNING)
            
    def command_stopped(self):
        self.w.lbl_pgm_color.setStyleSheet(f'Background-color: {STOP_COLOR};')
        if self.w.btn_pause_spindle.isChecked():
            self.h['spindle-inhibit'] = False
            self.h['eoffset-count'] = 0
        self.pause_timer.stop()
        self.h['runtime-start'] = False
        self.h['runtime-pause'] = False
        self.update_runtime()
        self.w.btn_pause.setEnabled(True)
        self.add_status("Program manually aborted")
        ACTION.ensure_mode(linuxcnc.MODE_MANUAL)

    def user_system_changed(self, data):
        sys = self.system_list[int(data) - 1]
        self.w.systemtoolbutton.setText(sys)
        txt = sys.replace('.', '_')
        self.w["action_" + txt.lower()].setChecked(True)
        self.add_status(f"User system changed to {sys}")

    def metric_mode_changed(self, mode):
        if mode:
            self.add_status("Switched to metric units")
        else:
            self.add_status("Switched to imperial units")
        units = "METRIC" if mode else "IMPERIAL"
        self.w.lineEdit_program_units.setText(units)

    def tool_changed(self, tool):
        self.current_tool = tool
        self.w.lineEdit_tool_in_spindle.setText(str(tool))
        LOG.debug(f"Tool changed to {self.current_tool}")
        self.tool_db.set_checked_tool(tool)
        icon = self.tool_db.get_tool_data(tool, "ICON")
        if icon is None or icon == "undefined":
            self.w.lbl_tool_image.setText("Image\nUndefined")
        else:
            icon_file = os.path.join(PATH.CONFIGPATH, 'tool_icons/' + icon)
            self.w.lbl_tool_image.setPixmap(QPixmap(icon_file))
        maxz  = self.tool_db.get_tool_data(tool, "LENGTH")
        rtime = self.tool_db.get_tool_data(tool, "TIME")
        text = "---" if maxz is None else str(maxz)
        self.w.lineEdit_max_depth.setText(text)
        text = "---" if rtime is None else f"{rtime:5.1f}"
        self.w.lineEdit_acc_time.setText(text)

    def file_loaded(self, filename):
        if filename is not None:
            self.add_status(f"Loaded file {filename}")
            self.w.progressBar.reset()
            self.last_loaded_program = filename
            self.current_loaded_program = filename
            self.w.lineEdit_runtime.setText("00:00:00")
        else:
            self.add_status("Filename not valid", WARNING)

    def percent_loaded_changed(self, pc):
        if self.progress == pc: return
        self.progress = pc
        if pc < 0:
            self.w.progressBar.setValue(0)
            self.w.progressBar.setFormat('PROGRESS')
        else:
            self.w.progressBar.setValue(pc)
            self.w.progressBar.setFormat(f'LOADING: {pc}%')

    def percent_done_changed(self, pc):
        if self.progress == pc: return
        self.progress = pc
        if pc < 0:
            self.w.progressBar.setValue(0)
            self.w.progressBar.setFormat('PROGRESS')
        else:
            self.w.progressBar.setValue(pc)
            self.w.progressBar.setFormat(f'PROGRESS: {pc}%')

    def homed(self, obj, joint):
        i = int(joint)
        axis = INFO.GET_NAME_FROM_JOINT.get(i).lower()
        try:
            widget = self.w[f"dro_axis_{axis}"]
            widget.setProperty('homed', True)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        except:
            pass

    def all_homed(self, obj):
        self.w.btn_home_all.setText("ALL\nHOMED")
        self.w.btn_home_all.setProperty('homed', True)
        self.w.btn_home_all.style().unpolish(self.w.btn_home_all)
        self.w.btn_home_all.style().polish(self.w.btn_home_all)
        if self.first_turnon is True:
            self.first_turnon = False
            if self.w.chk_reload_tool.isChecked():
                command = f"M61 Q{self.reload_tool}"
                ACTION.CALL_MDI(command)
            if self.last_loaded_program is not None and self.w.chk_reload_program.isChecked():
                if os.path.isfile(self.last_loaded_program):
                    self.w.cmb_gcode_history.addItem(self.last_loaded_program)
                    self.w.cmb_gcode_history.setCurrentIndex(self.w.cmb_gcode_history.count() - 1)
                    ACTION.OPEN_PROGRAM(self.last_loaded_program)
        ACTION.SET_MANUAL_MODE()
        self.w.manual_mode_button.setChecked(True)
        # enable camera buttons according to SETTINGS
        self.w.btn_ref_camera.setEnabled(self.w.chk_use_camera.isChecked())
        self.add_status("All axes homed")

    def not_all_homed(self, obj, list):
        self.w.btn_home_all.setText("HOME\nALL")
        self.w.btn_home_all.setProperty('homed', False)
        self.w.btn_home_all.style().unpolish(self.w.btn_home_all)
        self.w.btn_home_all.style().polish(self.w.btn_home_all)

    def update_runtime(self):
        hours = self.h['runtime-hours']
        minutes = self.h['runtime-minutes']
        seconds = self.h['runtime-seconds']
        self.w.lineEdit_runtime.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    def pause_changed(self, state):
        if not STATUS.is_auto_mode(): return
        if state:
            self.w.btn_pause.setText('  RESUME')
            self.w.lbl_pgm_color.setStyleSheet(f'Background-color: {PAUSE_COLOR};')
        else:
            self.w.btn_pause.setText('  PAUSE')
            self.w.lbl_pgm_color.setStyleSheet(f'Background-color: {RUN_COLOR};')
        self.add_status(f'Program paused set {state}')

    def add_external_status(self, message, option):
        level = option.get('LEVEL', STATUS.DEFAULT)
        log = option.get('LOG', True)
        msg = message.get('SHORTTEXT', '')
        self.add_status(msg, level)

    def update_gcode_properties(self, props):
        # substitute nice looking text:
        property_names = {
            'name': "Name:", 'size': "Size:",
            'tools': "Tool order:", 'g0': "Rapid distance:",
            'g1': "Feed distance:", 'g': "Total distance:",
            'run': "Run time:",'machine_unit_sys':"Machine Unit System:",
            'x': "X bounds:",'x_zero_rxy':'X @ Zero Rotation:',
            'y': "Y bounds:",'y_zero_rxy':'Y @ Zero Rotation:',
            'z': "Z bounds:",'z_zero_rxy':'Z @ Zero Rotation:',
            'a': "A bounds:", 'b': "B bounds:",
            'c': "C bounds:",'toollist':'Tool Change List:',
            'gcode_units':"Gcode Units:"
        }
        if not props: return
        text = ''
        for i in props:
            text += f'{property_names[i]} {props[i]}\n'
        self.setup_utils.show_gcode_properties(text)
        # update estimated runtime
        value, units = props['run'].split(' ')
        if units == 'Seconds':
            runtime = float(value)
        elif units == 'Minutes':
            runtime = float(value) * 60
        else:
            self.w.lineEdit_runtime_estimate.setText('')
            return
        hours, remainder = divmod(int(runtime), 3600)
        minutes, seconds = divmod(remainder, 60)
        text = f'{hours:02d}:{minutes:02d}:{seconds:02d}'
        self.w.lineEdit_runtime_estimate.setText(text)
        # send data to zlevel compensation module
        zdata = (props['x'], props['y'], props['gcode_units'])
        if self.zlevel is None: return
        self.zlevel.set_comp_area(zdata)

    def hard_limit_tripped(self, obj, tripped, list_of_tripped):
        self.add_status("Hard limits tripped", ERROR)
        self.w.chk_override_limits.setEnabled(tripped)
        if not tripped:
            self.w.chk_override_limits.setChecked(False)

    # keep check button in synch of external changes
    def _check_override_limits(self,state,data):
        if 0 in data:
            self.w.chk_override_limits.setChecked(False)
        else:
            self.w.chk_override_limits.setChecked(True)
    
    #######################
    # CALLBACKS FROM FORM #
    #######################

    # main button bar
    def main_tab_changed(self, btn):
        index = btn.property("index")
        title = btn.property("title")
        if index is None: return
        spindle_inhibit = False
        if STATUS.is_auto_mode() and index != TAB_SETTINGS:
            self.add_status("Cannot switch pages while in AUTO mode", WARNING)
            self.w.main_tab_widget.setCurrentIndex(TAB_MAIN)
            self.w.btn_main.setChecked(True)
            self.w.groupBox_preview.setTitle(self.w.btn_main.property("title"))
            return
        if index == TAB_PROBE:
            spindle_inhibit = self.w.chk_inhibit_spindle.isChecked()
            ACTION.CALL_MDI_WAIT("M5", mode_return=True)
        elif index == TAB_UTILS:
            if title == "UTILITIES":
                self.add_status('Select a utility from the drop down list')
                self.w.btn_utils.setChecked(False)
                return
        elif index == TAB_ABOUT:
            if title == 'ABOUT':
                self.add_status('Select an ABOUT topic from the drop down list')
                self.w.btn_about.setChecked(False)
                return
        self.w.mdihistory.MDILine.spindle_inhibit(spindle_inhibit)
        self.h['spindle-inhibit'] = spindle_inhibit
        self.w.main_tab_widget.setCurrentIndex(index)
        self.w.groupBox_preview.setTitle(title)

    def update_utils_button(self, text):
        try:
            idx = self.util_list.index(text)
        except ValueError:
            self.add_status(f'{text} not found in utilities list', ERROR)
            return
        self.w.btn_utils.setText(text.replace(" ", "\n"))
        self.w.btn_utils.setProperty('title', text + ' UTILITY')
        self.w.stackedWidget_utils.setCurrentIndex(idx)
        self.w.btn_utils.setChecked(True)
        self.main_tab_changed(self.w.btn_utils)

    def update_about_button(self, text):
        self.w.btn_about.setProperty('title', self.about_dict[text])
        fname = os.path.join(HELP, 'about_' + text + '.html')
        if os.path.dirname(fname):
            url = QUrl("file:///" + fname)
            self.web_page_about.load(url)
        else:
            self.add_status(f"About file {fname} not found", WARNING)
        self.w.btn_about.setChecked(True)
        self.main_tab_changed(self.w.btn_about)

    # preview frame
    def btn_dimensions_changed(self, state):
        self.w.gcodegraphics.show_extents_option = state
        self.w.gcodegraphics.clear_live_plotter()

    # gcode frame
    def cmb_gcode_history_activated(self):
        if self.w.cmb_gcode_history.currentIndex() == 0: return
        filename = self.w.cmb_gcode_history.currentText()
        if filename == self.last_loaded_program:
            self.add_status("Selected program is already loaded", WARNING)
        else:
            ACTION.OPEN_PROGRAM(filename)

    def gcode_widget_changed(self, idx):
        self.w.groupBox_gcode.setTitle(self.gcode_titles[idx])

    # program frame
    def btn_run_pressed(self):
        if STATUS.is_auto_running():
            self.add_status("Program is already running", WARNING)
            return
        if self.current_loaded_program is None:
            self.add_status("No program has been loaded", WARNING)
            return
        self.w.lbl_pgm_color.setStyleSheet(f'Background-color: {RUN_COLOR};')
        self.w.lbl_feedrate.setStyleSheet("color: #00FF00;")
        if self.start_line <= 1:
            ACTION.RUN(0)
        else:
            # instantiate run from line preset dialog
            info = f'Running From Line: {self.start_line}'
            mess = {'NAME' : 'RUNFROMLINE',
                    'TITLE' : 'Preset Dialog',
                    'ID' : '_RUNFROMLINE',
                    'MESSAGE' : info,
                    'LINE' : self.start_line,
                    'NONBLOCKING' : True}
            ACTION.CALL_DIALOG(mess)
        self.add_status(f"Started {self.current_loaded_program} from line {self.start_line}")
        self.h['runtime-start'] = True

    def btn_stop_pressed(self):
        if STATUS.is_auto_paused():
            self.pause_timer.stop()
            self.h['runtime-start'] = False
            self.h['runtime-pause'] = False
            self.update_runtime()
        self.w.btn_pause.setEnabled(True)
        ACTION.ABORT()
        self.add_status("Program manually aborted")

    def btn_pause_pressed(self):
        if STATUS.is_on_and_idle(): return
        if STATUS.is_auto_paused():
            self.h['runtime-pause'] = False
            ACTION.PAUSE()
        else:
            self.h['runtime-pause'] = True
            ACTION.PAUSE()
            if self.w.btn_pause_spindle.isChecked():
                self.pause_spindle()

    def btn_reload_pressed(self):
        if STATUS.is_auto_running():
            self.add_status("Cannot reload program while running", WARNING)
            return
        if self.last_loaded_program:
            self.w.progressBar.reset()
            self.add_status(f"Reloaded file {self.last_loaded_program}")
            ACTION.OPEN_PROGRAM(self.last_loaded_program)

    def pause_spindle(self):
        self.h['eoffset-count'] = int(self.w.lineEdit_spindle_raise.text())
        self.h['spindle-inhibit'] = True
        self.w.btn_pause.setEnabled(False)
        self.add_status(f"Spindle paused at {self.w.lineEdit_runtime.text()}")
        # instantiate warning box
        info = "Press OK when ready to resume program.\nSpindle will lower when at-speed is achieved."
        mess = {'NAME': 'MESSAGE',
                'ICON': 'WARNING',
                'ID': '_wait_to_lower_',
                'GEONAME': '__message',
                'MESSAGE': 'SPINDLE PAUSED',
                'NONBLOCKING': True,
                'MORE': info,
                'TYPE': 'OK'}
        ACTION.CALL_DIALOG(mess)

    def btn_pause_spindle_clicked(self, state):
        if not state and not self.w.btn_enable_comp.isChecked():
            self.w.lineEdit_eoffset.setText("DISABLED")
        text = "enabled" if state else "disabled"
        self.add_status("Spindle pause " + text)

    def btn_enable_comp_clicked(self, state):
        if state:
            fname = self.zlevel.get_map()
            if fname is None:
                self.add_status("No map file loaded - go to UTILS -> ZLEVEL and load a map file", WARNING)
                self.w.btn_enable_comp.setChecked(False)
                return
            if not os.path.isfile(fname):
                self.add_status(f"No such file - {fname}", WARNING)
                self.w.btn_enable_comp.setChecked(False)
                return
            if not QHAL.hal.component_exists("compensate"):
                self.add_status("Z level compensation HAL component not loaded", ERROR)
                self.w.btn_enable_comp.setChecked(False)
                return
            self.h['comp-on'] = True
            self.add_status(f"Z level compensation ON using {fname}")
        else:
            self.h['comp-on'] = False
            self.h['eoffset-count'] = 0
            self.add_status("Z level compensation OFF")
            if not self.w.btn_pause_spindle.isChecked():
                self.w.lineEdit_eoffset.setText("DISABLED")

    # jogging frame
    def jog_xy_pressed(self, btn):
        if btn == "C":
            text = "FAST" if self.slow_linear_jog is True else "SLOW"
            self.w.jog_xy.setCenterText(text)
            self.btn_linear_fast_clicked(not self.slow_linear_jog)
        else:
            axis = 'X' if btn in "LR" else 'Y'
            direction = 1 if btn in "RT" else -1
            self.w.jog_xy.set_highlight(axis, True)
            rate = int(self.w.adj_linear_jog.value())
            self.w.jog_xy.setCenterText(str(rate))
            ACTION.ensure_mode(linuxcnc.MODE_MANUAL)
            ACTION.DO_JOG(axis, direction)

    def jog_az_pressed(self, btn):
        if btn == "C":
            text = "FAST" if self.slow_angular_jog is True else "SLOW"
            self.w.jog_az.setCenterText(text)
            self.btn_angular_fast_clicked(not self.slow_angular_jog)
        else:
            if btn in "LR" and not "A" in self.axis_list: return
            axis = 'A' if btn in "LR" else 'Z'
            direction = 1 if btn in "RT" else -1
            self.w.jog_az.set_highlight(axis, True)
            rate = int(self.w.adj_linear_jog.value()) if axis == 'Z' else int(self.w.adj_angular_jog.value())
            self.w.jog_az.setCenterText(str(rate))
            ACTION.ensure_mode(linuxcnc.MODE_MANUAL)
            ACTION.DO_JOG(axis, direction)

    def jog_xy_released(self, btn):
        if btn == "C": return
        axis = 'X' if btn in "LR" else 'Y'
        self.w.jog_xy.set_highlight(axis, False)
        text = "SLOW" if self.slow_linear_jog is True else "FAST"
        self.w.jog_xy.setCenterText(text)
        if STATUS.get_jog_increment() == 0:
            ACTION.ensure_mode(linuxcnc.MODE_MANUAL)
            ACTION.DO_JOG(axis, 0)

    def jog_az_released(self, btn):
        if btn == "C": return
        if btn in "LR" and not "A" in self.axis_list: return
        axis = 'A' if btn in "LR" else 'Z'
        self.w.jog_az.set_highlight(axis, False)
        text = "SLOW" if self.slow_angular_jog is True else "FAST"
        self.w.jog_az.setCenterText(text)
        inc = STATUS.get_jog_increment_angular() if axis == 'A' else STATUS.get_jog_increment()
        if inc == 0:
            ACTION.ensure_mode(linuxcnc.MODE_MANUAL)
            ACTION.DO_JOG(axis, 0)
            
    def use_mpg_changed(self, state):
        self.h['mpg-disable'] = not state
        self.w.mpg_increment.setVisible(state)

    # TOOL frame
    def choose_tool(self):
        self.w.lineEdit_tool_in_spindle.clearFocus()
        mess = {'NAME' : 'TOOLCHOOSER',
                'ID' : '_toolchooser_'}
        ACTION.CALL_DIALOG(mess)

    def btn_touchoff_pressed(self):
        if STATUS.get_current_tool() == 0:
            self.add_status("Cannot touchoff with no tool loaded", WARNING)
            return
        if not STATUS.is_all_homed():
            self.add_status("Must be homed to perform tool touchoff", WARNING)
            return
        if self.w.chk_touchplate.isChecked():
            self.touchoff('touchplate')
        elif self.w.chk_auto_toolsensor.isChecked():
            self.touchoff('toolsensor')
        elif self.w.chk_manual_toolsensor.isChecked():
            self.touchoff('manual')
        else:
            self.add_status("Invalid touchoff method specified", WARNING)

    # DRO frame
    def show_macros_clicked(self, state):
        if state and not STATUS.is_auto_mode():
            show = False
            for i in range(10):
                if self.w[f'btn_macro{i}'].text() != '':
                    show = True
                self.w[f'btn_macro{i}'].setEnabled(bool(self.w[f'btn_macro{i}'].text() != ''))
            self.w.group1_macro_buttons.setVisible(show)
            show = False
            for i in range(10, 20):
                if self.w[f'btn_macro{i}'].text() != '':
                    show = True
                self.w[f'btn_macro{i}'].setEnabled(bool(self.w[f'btn_macro{i}'].text() != ''))
            self.w.group2_macro_buttons.setVisible(show)
        else:
            self.w.group1_macro_buttons.hide()
            self.w.group2_macro_buttons.hide()

    def systemtoolbutton_toggled(self, state):
        if state:
            STATUS.emit('dro-reference-change-request', 1)

    def btn_home_all_clicked(self, obj):
        if not STATUS.is_all_homed():
            ACTION.SET_MACHINE_HOMING(-1)
        else:
        # instantiate dialog box
            mess = {'NAME': 'MESSAGE',
                    'ID': '_unhome_',
                    'MESSAGE': 'UNHOME ALL',
                    'GEONAME': '__message',
                    'MORE': "Unhome All Axes?",
                    'NONBLOCKING': True,
                    'TYPE': 'YESNO'}
            ACTION.CALL_DIALOG(mess)

    def btn_rewind_clicked(self):
        stat = linuxcnc.stat()
        stat.poll()
        pos = stat.actual_position[3]
        joint = self.jog_from_name['A']
        frac = (pos + 180) % 360
        frac -= 180
        cmd = f"""G91
        G0 A-{frac}
        G90"""
        ACTION.CALL_MDI_WAIT(cmd, 10)
        ACTION.SET_MACHINE_HOMING(joint)
        self.add_status("Rotary axis rewound to 0")

    def btn_goto_location_clicked(self):
        dest = self.w.sender().property('location')
        man_mode = True if STATUS.is_man_mode() else False
        if dest == 'zero':
            x = 0
            y = 0
        elif dest == 'home':
            x = self.w.lbl_home_x.text()
            y = self.w.lbl_home_y.text()
        elif dest == 'sensor':
            x = self.w.lineEdit_sensor_x.text()
            y = self.w.lineEdit_sensor_y.text()
        else:
            return
        if dest == 'zero':
            cmd = ['G90', 'G53 G0 Z0', f'G0 X{x} Y{y}']
        else:
            cmd = ['G90', 'G53 G0 Z0', f'G53 G0 X{x} Y{y}']
        ACTION.CALL_BACKGROUND_MDI(cmd, label=f'Moving to {dest}', timeout=30)
        if man_mode:
            ACTION.SET_MANUAL_MODE()

    def btn_ref_laser_clicked(self):
        x = float(self.w.lineEdit_laser_x.text())
        y = float(self.w.lineEdit_laser_y.text())
        if not STATUS.is_metric_mode():
            x = x / 25.4
            y = y / 25.4
        self.add_status("Laser offsets set")
        command = f"G10 L20 P0 X{x:3.4f} Y{y:3.4f}"
        ACTION.CALL_MDI(command)

    def btn_ref_camera_clicked(self):
        x = float(self.w.lineEdit_camera_x.text())
        y = float(self.w.lineEdit_camera_y.text())
        if not STATUS.is_metric_mode():
            x = x / 25.4
            y = y / 25.4
        self.add_status("Camera offsets set")
        command = f"G10 L20 P0 X{x:3.4f} Y{y:3.4f}"
        ACTION.CALL_MDI(command)

    # override frame
    # this only works if jog adjusters are sliders
    def btn_linear_fast_clicked(self, state):
        self.slow_linear_jog = state
        step = 1 if state else 10
        page = 10 if state else 100
        if state is True:
            value  = int(self.w.adj_linear_jog.value()   / self.slow_jog_factor)
            maxval = int(self.w.adj_linear_jog.maximum() / self.slow_jog_factor)
        else:
            value  = int(self.w.adj_linear_jog.value()   * self.slow_jog_factor)
            maxval = int(self.w.adj_linear_jog.maximum() * self.slow_jog_factor)
        self.w.adj_linear_jog.setMaximum(maxval)
        self.w.adj_linear_jog.setValue(value)
        self.w.adj_linear_jog.setSingleStep(step)
        self.w.adj_linear_jog.setPageStep(page)

    # this only works if jog adjusters are sliders
    def btn_angular_fast_clicked(self, state):
        self.slow_angular_jog = state
        step = 1 if state else 10
        page = 10 if state else 100
        if state is True:
            value =  int(self.w.adj_angular_jog.value()   / self.slow_jog_factor)
            maxval = int(self.w.adj_angular_jog.maximum() / self.slow_jog_factor)
        else:
            value =  int(self.w.adj_angular_jog.value()   * self.slow_jog_factor)
            maxval = int(self.w.adj_angular_jog.maximum() * self.slow_jog_factor)
        self.w.adj_angular_jog.setMaximum(maxval)
        self.w.adj_angular_jog.setValue(value)
        self.w.adj_angular_jog.setSingleStep(step)
        self.w.adj_angular_jog.setPageStep(page)

    def preset_jograte(self, btn):
        if btn == self.w.btn_linear_50:
            self.w.adj_linear_jog.setValue(int(self.default_linear_jog_vel / 2))
        elif btn == self.w.btn_linear_100:
            self.w.adj_linear_jog.setValue(self.default_linear_jog_vel)
        elif btn == self.w.btn_angular_50:
            self.w.adj_angular_jog.setValue(int(self.default_angular_jog_vel / 2))
        elif btn == self.w.btn_angular_100:
            self.w.adj_angular_jog.setValue(self.default_angular_jog_vel)

    def adj_spindle_ovr_changed(self, value):
        frac = int(value * self.max_spindle_rpm / 100)
        self.w.gauge_spindle.set_threshold(frac)

    # FILE tab
    def copy_file(self):
        if self.w.sender() == self.w.btn_copy_right:
            source = self.w.filemanager_media.getCurrentSelected()
            target = self.w.filemanager_user.getCurrentSelected()
        elif self.w.sender() == self.w.btn_copy_left:
            source = self.w.filemanager_user.getCurrentSelected()
            target = self.w.filemanager_media.getCurrentSelected()
        else:
            return
        if source[1] is False:
            self.add_status("Specified source is not a file", WARNING)
            return
        self.source_file = source[0]
        if target[1] is True:
            self.destination_file = os.path.join(os.path.dirname(target[0]), os.path.basename(source[0]))
        else:
            self.destination_file = os.path.join(target[0], os.path.basename(source[0]))

        if os.path.isfile(self.destination_file) or os.path.isdir(self.destination_file):
            self.messagebox.setWindowTitle('Copy File')
            self.messagebox.setIcon(QMessageBox.Question)
            self.messagebox.setText(f'{self.destination_file} exists - overwrite?')
            self.messagebox.show()
        else:
            self.do_file_copy(self.messagebox.button(QMessageBox.Yes))

    def load_file(self):
        if self.w.btn_edit_gcode.isChecked():
            self.add_status('Cannot load file while GCode editing is active', WARNING)
            return
        fname = self.filemanager.getCurrentSelected()
        if fname[1] is False:
            self.add_status("Current selection is not a file", WARNING)
            return
        fname = fname[0]
        filename, file_extension = os.path.splitext(fname)
        if not INFO.program_extension_valid(fname):
            self.add_status(f"Unknown or invalid filename extension {file_extension}", WARNING)
            return
        if file_extension in ('.ngc', '.nc', 'tap', 'py'):
            self.w.cmb_gcode_history.addItem(fname)
            self.w.cmb_gcode_history.setCurrentIndex(self.w.cmb_gcode_history.count() - 1)
            ACTION.OPEN_PROGRAM(fname)
            self.w.main_tab_widget.setCurrentIndex(TAB_MAIN)
            self.w.btn_main.setChecked(True)
            self.w.groupBox_preview.setTitle(self.w.btn_main.property('title'))
            self.filemanager.recordBookKeeping()
        elif file_extension == '.html':
            self.setup_utils.show_html(fname)
            self.w.main_tab_widget.setCurrentIndex(TAB_UTILS)
            self.w.btn_utils.setChecked(True)
            self.add_status(f"Loaded HTML file : {fname}")
        elif file_extension == '.pdf':
            self.setup_utils.show_pdf(fname)
            self.w.main_tab_widget.setCurrentIndex(TAB_UTILS)
            self.w.btn_utils.setChecked(True)
            self.add_status(f"Loaded PDF file : {fname}")
        else:
            self.add_status(f"No action for {fname}", WARNING)

    def delete_file(self):
        fname = self.filemanager.getCurrentSelected()
        text = 'FILE' if fname[1] is True else 'FOLDER'
        self.deleteFile = fname[0]
        info = f"{self.deleteFile} will be moved to system Trash folder"
        mess = {'NAME': 'MESSAGE', 
                'ICON': 'WARNING',
                'ID': '_delete_',
                'MESSAGE': f'DELETE {text}?',
                'MORE': info,
                'TYPE': 'YESNO',
                'NONBLOCKING': True}
        ACTION.CALL_DIALOG(mess)

    def rename_file(self):
        fname = self.filemanager.getCurrentSelected()
        title = "Rename File" if fname[1] is True else "Rename Folder"
        label = "File" if fname[1] is True else "Folder"
        self.source_file = fname[0]
        self.input_dialog.setWindowTitle(title)
        self.input_dialog.setLabelText(f"Enter New {label} Name")
        self.input_dialog.setTextValue(self.source_file)
        self.input_dialog.show()

    def new_folder(self):
        current_dir = self.filemanager.getCurrentSelected()
        if current_dir[1] is True:
            current_path = os.path.dirname(current_dir[0])
        else:
            current_path = current_dir[0]
        self.input_dialog.setWindowTitle("New Folder")
        self.input_dialog.setLabelText("Enter New Folder Name")
        self.input_dialog.setTextValue(current_path)
        self.input_dialog.show()

    def edit_gcode(self):
        current_dir = self.filemanager.getCurrentSelected()
        if current_dir[1] is True:
            self.source_file = current_dir[0]
        else:
            self.add_status("Invalid file name", WARNING)
            return
        self.w.stackedWidget_file.setCurrentIndex(1)
        self.gcode_editor.editor.setModified(False)
        self.gcode_editor.openCall(self.source_file)

    def select_filemanager(self, state):
        self.filemanager = self.w.filemanager_user if state else self.w.filemanager_media

    def do_file_copy(self, btn):
        if btn == self.messagebox.button(QMessageBox.No):
            self.add_status(f"File {self.source_file} not copied")
            return
        try:
            shutil.copy2(self.source_file, self.destination_file)
            self.add_status(f"File {self.source_file} copied to {self.destination_file}")
        except FileNotFoundError:
            self.add_status(f"File {self.source_file} not found", ERROR)
        except PermissionError:
            self.add_status(f"Permission denied for {self.destination_file}", ERROR)
        except Exception as e:
            self.add_status(f"Copy file error: {e}", ERROR)

    def on_input_accepted(self):
        text = self.input_dialog.textValue()
        if self.input_dialog.windowTitle() == "Rename File":
            os.rename(self.source_file, text)
            self.add_status(f"Renamed file {self.source_file} to {text}")
        elif self.input_dialog.windowTitle() == "Rename Folder":
            os.rename(self.source_file, text)
            self.add_status(f"Renamed folder {self.source_file} to {text}")
        elif self.input_dialog.windowTitle() == "New Folder":
            try:
                os.makedirs(text, exist_ok = False)
                self.add_status(f"Folder {text} created successfully")
            except Exception as e:
                self.add_status(f"Folder create error: {e}", WARNING)

    def on_message_clicked(self, btn):
            self.do_file_copy()
                       
    # TOOL tab
    def btn_add_tool_pressed(self):
        if not STATUS.is_on_and_idle():
            self.add_status("Status must be ON and IDLE", WARNING)
            return
        array = [self.next_available, self.next_available, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 'New Tool']
        TOOL.ADD_TOOL(array)
        self.add_status(f"Added tool {self.next_available}")
        self.tool_db.add_tool(self.next_available)
        self.get_next_available()

    def btn_delete_tool_pressed(self):
        if not STATUS.is_on_and_idle():
            self.add_status("Status must be ON and IDLE", WARNING)
            return
        tools = self.get_checked_tools()
        if not tools:
            self.add_status("No tool selected to delete", WARNING)
            return
        if tools[0] == self.current_tool:
            ACTION.CALL_MDI('M61 Q0')
        TOOL.DELETE_TOOLS(tools)
        self.add_status(f"Deleted tool {tools[0]}")
        self.tool_db.delete_tool(tools[0])
        self.get_next_available()

    def btn_load_tool_pressed(self):
        tool = self.get_checked_tools()
        if len(tool) > 1:
            self.add_status("Select only 1 tool to load", ERROR)
        elif tool:
            ACTION.CALL_MDI_WAIT(f'M61 Q{tool[0]} G43', mode_return=True)
            self.add_status(f"Tool {tool[0]} loaded")
        else:
            self.add_status("No tool selected", WARNING)

    def btn_enable_edit_clicked(self, state):
        self.tool_db.set_edit_enable(state)

    def show_db_help_page(self):
        self.setup_utils.show_help_page(self.db_helpfile)

    # STATUS tab
    def btn_clear_status_clicked(self):
        STATUS.emit('update-machine-log', None, 'DELETE')

    def btn_save_log_pressed(self):
        if self.w.tabWidget_status.currentIndex() == 1:
            text = self.w.integrator_log.getLogText()
            target = "system"
        else:
            text = self.w.machine_log.getLogText()
            target = "machine"
        current_datetime = datetime.datetime.now()
        timestamp = current_datetime.strftime("%Y%m%d_%H%M%S")
        filename = f"{target}_{timestamp}.txt"
        self.add_status(f"Saving {target} log to {filename}")
        with open(filename, 'w') as f:
            f.write(text)

    # CAMVIEW tab
    def cam_zoom_changed(self, value):
        self.w.camview.scale = float(value) / 10

    def cam_dia_changed(self, value):
        self.w.camview.diameter = value

    def cam_rot_changed(self, value):
        self.w.camview.rotation = float(value) / 10

    # SETTINGS tab
    def override_limits_changed(self, state):
        # only toggle override if it's not in synch with the button
        if state and not STATUS.is_limits_override_set():
            self.add_status("Override limits set", WARNING)
            ACTION.TOGGLE_LIMITS_OVERRIDE()
        elif not state and STATUS.is_limits_override_set():
            error = ACTION.TOGGLE_LIMITS_OVERRIDE()
            # if override can't be released set the check button to reflect this
            if error == False:
                self.w.chk_override_limits.blockSignals(True)
                self.w.chk_override_limits.setChecked(True)
                self.w.chk_override_limits.blockSignals(False)
            else:
                self.add_status("Override limits not set")

    def use_camera_changed(self, state):
        self.w.btn_camera.setVisible(state)
        self.w.btn_ref_camera.setEnabled(state)
        self.w.camera_offset.setVisible(state)

    def edit_gcode_changed(self, state):
        if state:
            self.w.gcode_viewer.editMode()
        else:
            self.w.gcode_viewer.readOnlyMode()

    def chk_run_from_line_changed(self, state):
        if not state:
            self.w.btn_cycle_start.setText('  CYCLE START')
            self.start_line = 1

    def chk_use_basic_calc(self, state):
        if self.probe is None: return
        if self.probe.objectName() == 'basicprobe':
            self.probe.set_calc_mode(state)

    def touchoff_changed(self, state):
        if not state: return
        image = ''
        if self.w.chk_touchplate.isChecked():
            self.w.btn_touchoff.setText("  TOUCHPLATE")
            self.w.btn_touchoff.setToolTip("Auto probe Z down to touchplate")
            image = 'touch_plate.png'
        elif self.w.chk_auto_toolsensor.isChecked():
            self.w.btn_touchoff.setText("  AUTO TOUCHOFF")
            self.w.btn_touchoff.setToolTip("Auto probe Z down to tool sensor")
            image = 'tool_sensor.png'
        elif self.w.chk_manual_toolsensor.isChecked():
            self.w.btn_touchoff.setText("  MANUAL TOUCHOFF")
            self.w.btn_touchoff.setToolTip("Set workpiece Z0")
            image = 'tool_gauge.png'
        if image:
            image_file = os.path.join(PATH.CONFIGPATH, 'tool_icons/' + image)
            self.w.lbl_touchoff_image.setPixmap(QPixmap(image_file))
        self.w.lineEdit_touch_height.setReadOnly(not self.w.chk_touchplate.isChecked())
        self.w.lineEdit_sensor_height.setReadOnly(not self.w.chk_auto_toolsensor.isChecked())
        self.w.lineEdit_gauge_height.setReadOnly(not self.w.chk_manual_toolsensor.isChecked())

    #####################
    # GENERAL FUNCTIONS #
    #####################
    def tool_data_changed(self, new, old, roles):
        row = new.row()
        col = new.column()
        if col == 1:
            old_list = self.tool_list
            self.get_next_available()
            new_list = self.tool_list
            old_tno = list(set(old_list) - set(new_list))
            new_tno = list(set(new_list) - set(old_list))
            if len(new_tno) > 0:
                self.tool_db.update_tool_no(old_tno[0], new_tno[0])
        elif col == 15 or col == 19:
            self.tool_db.update_tool_data(row, col)

    def get_checked_tools(self):
        checked = self.w.tooloffsetview.get_checked_list()
        if checked: self.tool_db.set_checked_tool(checked[0])
        return checked

    def get_next_available(self):
        array = TOOL.GET_TOOL_ARRAY()
        tool_list = []
        for line in array:
            tool_list.append(line[0])
        self.tool_list = tool_list
        for tno in range(0, 100):
            if tno not in tool_list: break
        self.next_available = tno
        self.w.lineEdit_next_available.setText(str(tno))

    def max_power_edited(self):
        power = int(self.w.lineEdit_max_power.text())
        if power <= 0:
            self.w.lineEdit_max_power.setText(str(self.max_spindle_power))
            self.add_status("Max spindle power must be >0 - discarding change", WARNING)
        else:
            self.max_spindle_power = power
        self.w.lineEdit_max_power.clearFocus()

    def max_volts_edited(self):
        volts = int(self.w.lineEdit_max_volts.text())
        if volts <= 0:
            self.w.lineEdit_max_volts.setText(str(self.max_spindle_volts))
            self.add_status("Max spindle volts must be >0 - discarding change", WARNING)
        else:
            self.max_spindle_volts = volts
        self.w.lineEdit_max_volts.clearFocus()

    def max_amps_edited(self):
        amps = int(self.w.lineEdit_max_amps.text())
        if amps <= 0:
            self.w.lineEdit_max_amps.setText(str(self.max_spindle_amps))
            self.add_status("Max spindle amps must be >0 - discarding change.", WARNING)
        else:
            self.max_spindle_amps = amps
        self.w.lineEdit_max_amps.clearFocus()

    def show_selected_axis(self, obj):
        if self.w.chk_use_mpg.isChecked():
            self.w.jog_xy.set_highlight('X', bool(self.h['axis-select-x'] is True))
            self.w.jog_xy.set_highlight('Y', bool(self.h['axis-select-y'] is True))
            self.w.jog_az.set_highlight('Z', bool(self.h['axis-select-z'] is True))
            if 'A' in self.axis_list:
                self.w.jog_az.set_highlight('A', bool(self.h['axis-select-a'] is True))

    def touchoff(self, mode):
        if mode == 'touchplate':
            z_offset = self.w.lineEdit_touch_height.text()
        elif mode == 'toolsensor':
            z_offset = float(self.w.lineEdit_sensor_height.text()) - float(self.w.lineEdit_work_height.text())
            z_offset = str(z_offset)
        elif mode == "manual":
            z_offset = float(self.w.lineEdit_sensor_height.text()) - float(self.w.lineEdit_work_height.text())
            ACTION.CALL_MDI(f"G10 L20 P0 Z{z_offset:.3f}")
            return            
        else:
            return
        self.add_status(f"Touchoff to {mode} started")
        search_vel = self.w.lineEdit_search_vel.text()
        probe_vel = self.w.lineEdit_probe_vel.text()
        max_probe = self.w.lineEdit_max_probe.text()
        retract = self.w.lineEdit_retract.text()
        safe_z = self.w.lineEdit_zsafe.text()
        rtn = ACTION.TOUCHPLATE_TOUCHOFF(search_vel, probe_vel, max_probe, z_offset, retract, safe_z, \
                                         self.touchoff_return, \
                                         self.touchoff_error)
        if rtn == 0:
            self.add_status("Touchoff routine is already running", WARNING)

    def touchoff_return(self, data):
        if self.w.chk_auto_toolsensor.isChecked():
            ACTION.CALL_MDI_WAIT('G53 G0 Z0', mode_return=True)
        self.add_status("Touchoff routine returned success")
            
    def touchoff_error(self, data):
        self.add_status(data, WARNING)
        ACTION.SET_ERROR_MESSAGE(data)

    def spindle_pause_timer(self):
        if bool(self.h.hal.get_value('spindle.0.at-speed')):
            self.h['eoffset-count'] = 0
            self.w.btn_pause.setEnabled(True)
            self.add_status("Spindle pause resumed")
        else:
            self.pause_timer.start(1000)
        
    def kb_jog(self, state, axis, direction):
        if not STATUS.is_man_mode() or not STATUS.machine_is_on():
            self.add_status('Machine must be ON and in Manual mode to jog', WARNING)
            return
        if state == 0: direction = 0
        ACTION.DO_JOG(axis, direction)

    def add_status(self, message, level=DEFAULT, noLog=False):
        if level == WARNING:
            self.w.statusbar.setStyleSheet(f"color: {WARNING_COLOR};")
            message = 'WARNING: ' + message
            self.w.statusbar.showMessage(message, 10000)
            self.stat_warnings += 1
            self.w.lbl_stat_warnings.setText(f'{self.stat_warnings}')
        elif level == ERROR:
            self.w.statusbar.setStyleSheet(f"color: {ERROR_COLOR};")
            message = 'ERROR: ' + message
            self.w.statusbar.showMessage(message, 10000)
            self.stat_errors += 1
            self.w.lbl_stat_errors.setText(f'{self.stat_errors}')
        else:
            self.w.statusbar.showMessage(message)
            self.w.statusbar.setStyleSheet(self.statusbar_style)
        if not message == "" and noLog is False:
            STATUS.emit('update-machine-log', message, 'TIME')

    def statusbar_changed(self, message):
        if message == "":
            self.w.statusbar.setStyleSheet(self.statusbar_style)

    def enable_auto(self, state):
        if not STATUS.machine_is_on(): return
        if self.zlevel is not None:
            self.w.btn_enable_comp.setEnabled(not state)
        self.w.btn_pause_spindle.setEnabled(not state)
        self.w.btn_goto_sensor.setEnabled(not state)
        self.w.groupBox_jog_pads.setEnabled(not state)
        self.w.btn_cycle_start.setEnabled(state)
        self.w.lineEdit_spindle_raise.setReadOnly(state)
        if self.w.btn_show_macros.isChecked():
            self.show_macros_clicked(not state)
        if state:
            self.w.btn_main.setChecked(True)
            self.w.main_tab_widget.setCurrentIndex(TAB_MAIN)
            self.w.cmb_gcode_history.hide()
            self.w.btn_edit_gcode.setChecked(False)
            self.w.gcode_viewer.readOnlyMode()
            self.w.stackedWidget_gcode.setCurrentIndex(0)
        else:
            i = 1 if STATUS.is_mdi_mode() else 0
            self.w.stackedWidget_gcode.setCurrentIndex(i)
            self.w.cmb_gcode_history.show()

    def enable_onoff(self, state):
        text = "ON" if state else "OFF"
        self.add_status("Machine " + text)
        self.h['eoffset-count'] = 0
        if not state:
            self.w.groupBox_jog_pads.setEnabled(False)
            self.w.btn_cycle_start.setEnabled(False)

    def set_start_line(self, line):
        if self.w.chk_run_from_line.isChecked():
            self.start_line = line
            self.w.btn_cycle_start.setText(f"  CYCLE START\n  FROM LINE {self.start_line}")
        else:
            self.start_line = 1

    def use_keyboard(self):
        if self.w.chk_use_keyboard.isChecked():
            return True
        else:
            self.add_status('Keyboard shortcuts are disabled', WARNING)
            return False

    def stop_timer(self):
        self.w.lbl_pgm_color.setStyleSheet(f'Background-color: {STOP_COLOR};')
        self.w.lbl_feedrate.setStyleSheet(self.feedrate_style)
        if self.h['runtime-start'] is True:
            self.h['runtime-start'] = False
            self.add_status(f"Run timer stopped at {self.w.lineEdit_runtime.text()}")
            if self.current_tool > 0:
                rtime = self.w.lineEdit_runtime.text().split(':')
                mtime = (float(rtime[0]) * 60) + float(rtime[1]) + (float(rtime[2]) / 60)
                self.tool_db.update_tool_time(self.current_tool, mtime)
                rtime = self.tool_db.get_tool_data(self.current_tool, "TIME")
                text = "---" if rtime is None else f"{rtime:5.1f}"
                self.w.lineEdit_acc_time.setText(text)

    #####################
    # KEY BINDING CALLS #
    #####################

    def on_keycall_ESTOP(self,event,state,shift,cntrl):
        if state:
            self.w.btn_estop.setChecked(False)

    def on_keycall_POWER(self,event,state,shift,cntrl):
        if state:
            ACTION.SET_MACHINE_STATE(not STATUS.machine_is_on())

    def on_keycall_ABORT(self,event,state,shift,cntrl):
        if state:
            ACTION.ABORT()

    def on_keycall_HOME(self,event,state,shift,cntrl):
        if state and not STATUS.is_all_homed() and self.use_keyboard():
            ACTION.SET_MACHINE_HOMING(-1)

    def on_keycall_PAUSE(self,event,state,shift,cntrl):
        if state and self.use_keyboard():
            self.btn_pause_pressed()

    def on_keycall_XPOS(self,event,state,shift,cntrl):
        if self.use_keyboard():
            self.kb_jog(state, 'X', 1)

    def on_keycall_XNEG(self,event,state,shift,cntrl):
        if self.use_keyboard():
            self.kb_jog(state, 'X', -1)

    def on_keycall_YPOS(self,event,state,shift,cntrl):
        if self.use_keyboard():
            self.kb_jog(state, 'Y', 1)

    def on_keycall_YNEG(self,event,state,shift,cntrl):
        if self.use_keyboard():
            self.kb_jog(state, 'Y', -1)

    def on_keycall_ZPOS(self,event,state,shift,cntrl):
        if self.use_keyboard():
            self.kb_jog(state, 'Z', 1)

    def on_keycall_ZNEG(self,event,state,shift,cntrl):
        if self.use_keyboard():
            self.kb_jog(state, 'Z', -1)
    
    def on_keycall_APOS(self,event,state,shift,cntrl):
        if self.use_keyboard() and 'A' in self.axis_list:
            self.kb_jog(state, 'A', 1)

    def on_keycall_ANEG(self,event,state,shift,cntrl):
        if self.use_keyboard() and 'A' in self.axis_list:
            self.kb_jog(state, 'A', -1)

    def on_keycall_F4(self,event,state,shift,cntrl):
        if state:
            mess = {'NAME':'CALCULATOR', 'TITLE':'Calculator', 'ID':'_calculator_'}
            ACTION.CALL_DIALOG(mess)

    def on_keycall_F12(self,event,state,shift,cntrl):
        if state:
            self.styleeditor.load_dialog()

    ##############################
    # required class boiler code #
    ##############################
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)

################################
# required handler boiler code #
################################

def get_handlers(halcomp, widgets, paths):
    return [HandlerClass(halcomp, widgets, paths)]
