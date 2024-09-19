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
import datetime
import requests
import linuxcnc
from connections import Connections
from PyQt5 import QtCore, QtWidgets, QtGui, uic
from PyQt5.QtCore import QRegExp
from PyQt5.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor
from PyQt5.QtWidgets import QMessageBox
from qtvcp.widgets.gcode_editor import GcodeEditor as GCODE
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
VERSION = '2.0.5'

# constants for main pages
TAB_MAIN = 0
TAB_FILE = 1
TAB_OFFSETS = 2
TAB_TOOL = 3
TAB_STATUS = 4
TAB_PROBE = 5
TAB_CAMVIEW = 6
TAB_UTILS = 7
TAB_SETTINGS = 8
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
    def __init__(self, parent=None):
        super(Highlighter, self).__init__(parent)
        self.highlightingRules = []

        warningLineFormat = QTextCharFormat()
        errorLineFormat = QTextCharFormat()
        warningLineFormat.setForeground(QColor(WARNING_COLOR))
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


class HandlerClass:
    def __init__(self, halcomp, widgets, paths):
        self.h = halcomp
        self.w = widgets
        self.valid = QtGui.QDoubleValidator(-999.999, 999.999, 3)
        self.styleeditor = SSE(widgets, paths, addBuiltinStyles=False)
        self.settings_checkboxes = []
        self.touchoff_checkboxes = []
        self.settings_offsets = []
        self.settings_spindle = []
        self.settings_probe = []
        self.settings_touchoff = []
        KEYBIND.add_call('Key_F4', 'on_keycall_F4')
        KEYBIND.add_call('Key_F12','on_keycall_F12')
        KEYBIND.add_call('Key_Pause', 'on_keycall_PAUSE')
        KEYBIND.add_call('Key_Any', 'on_keycall_PAUSE')
        # references to utility objects to be initialized
        self.probe = None
        self.tool_db = None
        self.zlevel = None
        # some global variables
        self.current_tool = 0
        self.tool_list = []
        self.next_available = 0
        self.pause_dialog = None
        self.about_html = os.path.join(PATH.CONFIGPATH, "help_files/about.html")
        self.start_line = 0
        self.runtime_save = ""
        self.runtime_color = None
        self.feedrate_color = None
        self.statusbar_color = '#F0F0F0'
        self.stat_warnings = 0
        self.stat_errors = 0
        self.max_spindle_power = 100
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
        self.macros_defined = 0
        self.source_file = ""
        self.destination_file = ""
        self.pause_delay = 0
        self.pause_timer = QtCore.QTimer()
        self.icon_btns = {'action_exit': 'SP_BrowserStop'}

        self.adj_list = ['maxvel_ovr', 'rapid_ovr', 'feed_ovr', 'spindle_ovr']

        self.unit_label_list = ["zoffset_units", "max_probe_units", "retract_units", "zsafe_units", "probe_start_units",
                                "touch_units", "sensor_units", "gauge_units", "rotary_units", "mpg_units"]

        self.unit_speed_list = ["search_vel_units", "probe_vel_units"]

        self.lineedit_list = ["work_height", "touch_height", "sensor_height", "laser_x", "laser_y", "camera_x",
                              "camera_y", "search_vel", "probe_vel", "retract", "max_probe", "eoffset", "eoffset_count",
                              "sensor_x", "sensor_y", "zsafe", "probe_x", "probe_y", "rotary_height", "gauge_height"]

        self.axis_a_list = ["dro_axis_a", "lbl_max_angular", "lbl_max_angular_vel", "angular_increment",
                            "action_zero_a", "btn_rewind_a", "action_home_a", "widget_angular_jog",
                            "lbl_rotary_height", "lineEdit_rotary_height", "lbl_rotary_units"]

        STATUS.connect('state-estop', lambda w: self.w.btn_estop.setText("ESTOP\nACTIVE"))
        STATUS.connect('state-estop-reset', lambda w: self.w.btn_estop.setText("ESTOP\nRESET"))
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
        STATUS.connect('command-stopped', self.command_stopped)
        STATUS.connect('file-loaded', lambda w, filename: self.file_loaded(filename))
        STATUS.connect('all-homed', self.all_homed)
        STATUS.connect('not-all-homed', self.not_all_homed)
        STATUS.connect('interp-idle', lambda w: self.stop_timer())
        STATUS.connect('override-limits-changed', lambda w, state, data: self._check_override_limits(state, data))

    def class_patch__(self):
#        self.old_fman = FM.load
        FM.load = self.load_code

    def initialized__(self):
        self.init_pins()
        self.init_preferences()
        self.init_tooldb()
        self.init_widgets()
        self.init_probe()
        self.init_utils()
        self.init_macros()
        self.init_adjustments()
        self.check_for_updates()
        self.runtime_color = self.w.lineEdit_runtime.palette().color(self.w.lineEdit_runtime.foregroundRole())
        self.w.stackedWidget_gcode.setCurrentIndex(0)
        self.w.stackedWidget_log.setCurrentIndex(0)
        self.w.btn_dimensions.setChecked(True)
        self.w.page_buttonGroup.buttonClicked.connect(self.main_tab_changed)
        self.w.preset_buttonGroup.buttonClicked.connect(self.preset_jograte)
        self.w.filemanager.onUserClicked()
        self.use_mpg_changed(self.w.chk_use_mpg.isChecked())
        self.use_camera_changed(self.w.chk_use_camera.isChecked())
        self.touchoff_changed(True)
        if self.probe is not None: self.probe_offset_edited()
        # determine if A axis widgets should be visible or not
        if not "A" in self.axis_list:
            for item in self.axis_a_list:
                self.w[item].hide()
        # set validators for lineEdit widgets
        for val in self.lineedit_list:
            self.w['lineEdit_' + val].setValidator(self.valid)
        self.w.lineEdit_max_power.setValidator(QtGui.QIntValidator(0, 9999))
        self.w.lineEdit_spindle_delay.setValidator(QtGui.QIntValidator(0, 99))
        # set unit labels according to machine mode
        self.w.lbl_machine_units.setText("METRIC" if INFO.MACHINE_IS_METRIC else "IMPERIAL")
        for i in self.unit_label_list:
            self.w['lbl_' + i].setText(self.machine_units)
        for i in self.unit_speed_list:
            self.w['lbl_' + i].setText(self.machine_units + "/MIN")
        self.w.setWindowFlags(QtCore.Qt.FramelessWindowHint)
        # connect all signals to corresponding slots
        connect = Connections(self, self.w)
        self.w.tooloffsetview.tablemodel.layoutChanged.connect(self.get_checked_tools)
        self.w.tooloffsetview.tablemodel.dataChanged.connect(lambda new, old, roles: self.tool_data_changed(new, old, roles))
        self.w.statusbar.messageChanged.connect(self.statusbar_changed)


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
        self.settings_checkboxes = self.w.groupBox_operational.findChildren(QtWidgets.QCheckBox)
        for checkbox in self.settings_checkboxes:
            checkbox.setChecked(self.w.PREFS_.getpref(checkbox.objectName(), False, bool, 'CUSTOM_FORM_ENTRIES'))
        # touchoff checkboxes
        self.touchoff_checkboxes = self.w.frame_touchoff.findChildren(QtWidgets.QCheckBox)
        for checkbox in self.touchoff_checkboxes:
            checkbox.setChecked(self.w.PREFS_.getpref(checkbox.objectName(), False, bool, 'CUSTOM_FORM_ENTRIES'))
        # offsets settings
        self.settings_offsets = self.w.frame_locations.findChildren(QtWidgets.QLineEdit)
        for offset in self.settings_offsets:
            offset.setText(self.w.PREFS_.getpref(offset.objectName(), '10', str, 'CUSTOM_FORM_ENTRIES'))
        # spindle settings
        self.settings_spindle = self.w.frame_spindle_settings.findChildren(QtWidgets.QLineEdit)
        for spindle in self.settings_spindle:
            spindle.setText(self.w.PREFS_.getpref(spindle.objectName(), '10', str, 'CUSTOM_FORM_ENTRIES'))
        self.max_spindle_power = float(self.w.lineEdit_max_power.text())
        # probe settings
        self.settings_probe = self.w.frame_probe_parameters.findChildren(QtWidgets.QLineEdit)
        for probe in self.settings_probe:
            probe.setText(self.w.PREFS_.getpref(probe.objectName(), '10', str, 'CUSTOM_FORM_ENTRIES'))
        # touchoff settings
        self.settings_touchoff = self.w.frame_touchoff.findChildren(QtWidgets.QLineEdit)
        for touchoff in self.settings_touchoff:
            touchoff.setText(self.w.PREFS_.getpref(touchoff.objectName(), '10', str, 'CUSTOM_FORM_ENTRIES'))
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
        for offset in self.settings_offsets:
            self.w.PREFS_.putpref(offset.objectName(), offset.text(), str, 'CUSTOM_FORM_ENTRIES')
        for spindle in self.settings_spindle:
            self.w.PREFS_.putpref(spindle.objectName(), spindle.text(), str, 'CUSTOM_FORM_ENTRIES')
        for probe in self.settings_probe:
            self.w.PREFS_.putpref(probe.objectName(), probe.text(), str, 'CUSTOM_FORM_ENTRIES')
        for touchoff in self.settings_touchoff:
            self.w.PREFS_.putpref(touchoff.objectName(), touchoff.text(), str, 'CUSTOM_FORM_ENTRIES')
        if self.last_loaded_program is not None:
            self.w.PREFS_.putpref('last_loaded_directory', os.path.dirname(self.last_loaded_program), str, 'BOOK_KEEPING')
            self.w.PREFS_.putpref('last_loaded_file', self.last_loaded_program, str, 'BOOK_KEEPING')
        self.w.PREFS_.putpref('Tool to load', STATUS.get_current_tool(), int, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Work Height', self.w.lineEdit_work_height.text(), float, 'CUSTOM_FORM_ENTRIES')

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
        self.w.cmb_gcode_history.view().setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        # gcode editor mode
        self.w.gcode_viewer.readOnlyMode()
        # ABOUT pages
        from lib.setup_about import Setup_About
        self.about_pages = Setup_About(self.w, self)
        self.about_pages.init_about()
        # mdi history
        self.w.mdihistory.MDILine.setFixedHeight(30)
        self.w.mdihistory.MDILine.setPlaceholderText('MDI:')
        self.use_mdi_keyboard_changed(self.w.chk_use_mdi_keyboard.isChecked())
        self.w.cmb_mdi_texts.addItem("SELECT")
        self.w.cmb_mdi_texts.addItem("HALSHOW")
        self.w.cmb_mdi_texts.addItem("HALMETER")
        self.w.cmb_mdi_texts.addItem("HALSCOPE")
        self.w.cmb_mdi_texts.addItem("STATUS")
        self.w.cmb_mdi_texts.addItem("CLASSICLADDER")
        self.w.cmb_mdi_texts.addItem("CALIBRATION")
        self.w.cmb_mdi_texts.addItem("PREFERENCE")
        self.w.cmb_mdi_texts.addItem("CLEAR HISTORY")
        # set calculator mode for menu buttons
        for i in ("x", "y", "z"):
            self.w["axistoolbutton_" + i].set_dialog_code('CALCULATOR')
        # disable mouse wheel events on comboboxes
        self.w.cmb_gcode_history.wheelEvent = lambda event: None
        self.w.cmb_icon_select.wheelEvent = lambda event: None
        self.w.jogincrements_linear.wheelEvent = lambda event: None
        self.w.jogincrements_angular.wheelEvent = lambda event: None
        # turn off table grids
        self.w.filemanager.table.setShowGrid(False)
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
        # util page scroll buttons
        pixmap = QtGui.QPixmap('qtdragon/images/Right_arrow.png')
        self.w.btn_util_right.setIcon(QtGui.QIcon(pixmap))
        pixmap = QtGui.QPixmap('qtdragon/images/Left_arrow.png')
        self.w.btn_util_left.setIcon(QtGui.QIcon(pixmap))
        # initialize jog joypads
        self.w.jog_xy.set_icon('L', 'image', 'qtdragon/images/x_minus_jog_button.png')
        self.w.jog_xy.set_icon('R', 'image', 'qtdragon/images/x_plus_jog_button.png')
        self.w.jog_xy.set_icon('T', 'image', 'qtdragon/images/y_plus_jog_button.png')
        self.w.jog_xy.set_icon('B', 'image', 'qtdragon/images/y_minus_jog_button.png')
        self.w.jog_az.set_icon('L', 'image', 'qtdragon/images/a_minus_jog_button.png')
        self.w.jog_az.set_icon('R', 'image', 'qtdragon/images/a_plus_jog_button.png')
        self.w.jog_az.set_icon('T', 'image', 'qtdragon/images/z_plus_jog_button.png')
        self.w.jog_az.set_icon('B', 'image', 'qtdragon/images/z_minus_jog_button.png')
        # only if override adjusters are sliders
        self.w.jog_xy.setFont(QtGui.QFont('Lato Heavy', 9))
        self.w.jog_az.setFont(QtGui.QFont('Lato Heavy', 9))
        self.w.jog_xy.setCenterText("FAST")
        self.w.jog_az.setCenterText("FAST")
        self.w.jog_xy.set_tooltip('C', 'Toggle FAST / SLOW linear jograte')
        self.w.jog_az.set_tooltip('C', 'Toggle FAST / SLOW angular jograte')
        # apply standard button icons
        for key in self.icon_btns:
            style = self.w[key].style()
            icon = style.standardIcon(getattr(QtWidgets.QStyle, self.icon_btns[key]))
            self.w[key].setIcon(icon)
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

    def init_tooldb(self):
        from lib.tool_db import Tool_Database
        self.tool_db = Tool_Database(self.w, self)
        self.db_helpfile = os.path.join(HELP, 'tooldb_help.html')
        self.tool_db.hal_init()
        self.btn_tool_db_clicked(False)

    def init_probe(self):
        probe = INFO.get_error_safe_setting('PROBE', 'USE_PROBE', 'none').lower()
        if probe == 'versaprobe':
            LOG.info("Using Versa Probe")
#            from qtvcp.widgets.versa_probe import VersaProbe
            from lib.versa_probe import VersaProbe
            self.probe = VersaProbe()
            self.probe.setObjectName('versaprobe')
        elif probe == 'basicprobe':
            LOG.info("Using Basic Probe")
            from lib.basic_probe import BasicProbe
            self.probe = BasicProbe(self)
            self.probe.setObjectName('basicprobe')
        else:
            LOG.info("No valid probe widget specified")
            self.w.btn_probe.hide()
        if self.probe is not None:
            self.w.probe_layout.addWidget(self.probe)
            self.probe.hal_init()
            self.w.lineEdit_probe_x.editingFinished.connect(self.probe_offset_edited)
            self.w.lineEdit_probe_y.editingFinished.connect(self.probe_offset_edited)

    def init_utils(self):
        from lib.setup_utils import Setup_Utils
        self.setup_utils = Setup_Utils(self.w, self)
        self.setup_utils.init_utils()
        if self.zlevel is None:
            self.w.btn_enable_comp.setEnabled(False)
        self.get_next_available()
        self.tool_db.update_tools(self.tool_list)

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
                self.macros_defined += 1
            except:
                button.setText('')
                button.setEnabled(False)
        self.w.group1_macro_buttons.hide()
        self.w.group2_macro_buttons.hide()
        state = self.w.chk_show_macros.isChecked()
        self.chk_show_macros_changed(state)

    def init_adjustments(self):
        # modify the status adjustment bars to have custom icons
        icon = QtGui.QIcon(os.path.join(IMAGES, 'arrow_left.png'))
        icon_size = 24
        for item in self.adj_list:
            btn = self.w[f"adj_{item}"].tb_down
            btn.setArrowType(QtCore.Qt.NoArrow)
            btn.setIcon(icon)
            btn.setIconSize(QtCore.QSize(icon_size, icon_size))
        icon = QtGui.QIcon(os.path.join(IMAGES, 'arrow_right.png'))
        for item in self.adj_list:
            btn = self.w[f"adj_{item}"].tb_up
            btn.setArrowType(QtCore.Qt.NoArrow)
            btn.setIcon(icon)
            btn.setIconSize(QtCore.QSize(icon_size, icon_size))
        # slow the timer down
        for item in self.adj_list:
            self.w[f"adj_{item}"].timer_value = 200

    def processed_key_event__(self, receiver, event, is_pressed, key, code, shift, cntrl):
        # when typing in MDI, we don't want keybinding to call functions
        # so we catch and process the events directly.
        # We do want ESC, F1 and F2 to call keybinding functions though
        if code not in(QtCore.Qt.Key_Escape, QtCore.Qt.Key_F1 , QtCore.Qt.Key_F2):
#                    QtCore.Qt.Key_F3,QtCore.Qt.Key_F4,QtCore.Qt.Key_F5):

            # search for the top widget of whatever widget received the event
            # then check if it's one we want the keypress events to go to
            flag = False
            receiver2 = receiver
            while receiver2 is not None and not flag:
                if isinstance(receiver2, QtWidgets.QDialog):
                    flag = True
                    break
                if isinstance(receiver2, QtWidgets.QLineEdit):
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

    def spindle_pwr_changed(self):
        # this calculation assumes a power factor of 0.8
        power = float(self.h['spindle-volts'] * self.h['spindle-amps'] * 1.386) # V x I x PF x sqrt(3)
        try: # in case of divide by zero
            pc_power = int((power / self.max_spindle_power) * 100)
            if pc_power > 100:
                pc_power = 100
            self.w.spindle_power.setValue(pc_power)
        except Exception as e:
            self.w.spindle_power.setValue(0)

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
                self.add_status(f"Error - {e}", WARNING)
            
    def command_stopped(self, obj):
        if self.w.btn_pause_spindle.isChecked():
            self.h['spindle-inhibit'] = False
            self.h['eoffset-count'] = 0

    def user_system_changed(self, data):
        sys = self.system_list[int(data) - 1]
        self.w.actionbutton_rel.setText(sys)
        txt = sys.replace('.', '_')
        self.w["action_" + txt.lower()].setChecked(True)

    def metric_mode_changed(self, mode):
        if mode:
            self.add_status("Switched to metric units")
        else:
            self.add_status("Switched to imperial units")
        units = "METRIC" if mode else "IMPERIAL"
        self.w.lineEdit_program_units.setText(units)

    def tool_changed(self, tool):
        self.current_tool = tool
        LOG.debug(f"Tool changed to {self.current_tool}")
        self.tool_db.set_checked_tool(tool)
        icon = self.tool_db.get_tool_data(tool, "ICON")
        if icon is None or icon == "undefined":
            self.w.lbl_tool_image.setText("Image\nUndefined")
        else:
            icon_file = os.path.join(PATH.CONFIGPATH, 'tool_icons/' + icon)
            self.w.lbl_tool_image.setPixmap(QtGui.QPixmap(icon_file))
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
        if index is None: return
        if index == self.w.main_tab_widget.currentIndex(): return
        spindle_inhibit = False
        if STATUS.is_auto_mode() and index != TAB_SETTINGS:
            self.add_status("Cannot switch pages while in AUTO mode", WARNING)
            self.w.main_tab_widget.setCurrentIndex(TAB_MAIN)
            self.w.btn_main.setChecked(True)
            self.w.groupBox_preview.setTitle(self.w.btn_main.text())
            return
        if index == TAB_STATUS:
            highlighter = Highlighter(self.w.machine_log)
        elif index == TAB_PROBE:
            spindle_inhibit = self.w.chk_inhibit_spindle.isChecked()
        self.w.mdihistory.MDILine.spindle_inhibit(spindle_inhibit)
        self.h['spindle-inhibit'] = spindle_inhibit
        self.w.main_tab_widget.setCurrentIndex(index)
        self.w.groupBox_preview.setTitle(btn.text())

    # preview frame
    def btn_dimensions_changed(self, state):
        self.w.gcodegraphics.show_extents_option = state
        self.w.gcodegraphics.clear_live_plotter()

    # gcode frame
    def cmb_gcode_history_clicked(self):
        if self.w.cmb_gcode_history.currentIndex() == 0: return
        filename = self.w.cmb_gcode_history.currentText()
        if filename == self.last_loaded_program:
            self.add_status("Selected program is already loaded", WARNING)
        else:
            ACTION.OPEN_PROGRAM(filename)

    def mdi_select_text(self):
        if self.w.cmb_mdi_texts.currentIndex() <= 0: return
        self.w.mdihistory.MDILine.setText(self.w.cmb_mdi_texts.currentText())
        self.w.cmb_mdi_texts.setCurrentIndex(0)

    def mdi_enter_pressed(self):
        if self.w.mdihistory.MDILine.text() == "CLEAR HISTORY":
            self.add_status("MDI history cleared")
        self.w.mdihistory.run_command()
        self.w.mdihistory.MDILine.clear()

    # program frame
    def btn_run_pressed(self):
        if STATUS.is_auto_running():
            self.add_status("Program is already running", WARNING)
            return
        if self.current_loaded_program is None:
            self.add_status("No program has been loaded", WARNING)
            return
        self.w.lbl_pgm_color.setStyleSheet(f'Background-color: {RUN_COLOR};')
        self.feedrate_color = self.w.lbl_feedrate.palette().color(self.w.lbl_feedrate.foregroundRole())
        self.w.lbl_feedrate.setStyleSheet('color: "#00FF00";')
        if self.start_line <= 1:
            ACTION.RUN(0)
        else:
            # instantiate run from line preset dialog
            info = f'<b>Running From Line: {self.start_line} <\b>'
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
            self.w.btn_pause.setText("  PAUSE")
            self.pause_timer.stop()
            self.pause_delay = 0
            self.h['runtime-start'] = False
            self.h['runtime-pause'] = False
            self.w.lineEdit_runtime.setStyleSheet(f"color; {self.runtime_color.name()};")
            self.update_runtime()
        ACTION.ABORT()
        ACTION.SET_MANUAL_MODE()
        self.add_status("Program manually aborted")

    def btn_pause_pressed(self):
        if STATUS.is_on_and_idle(): return
        if STATUS.is_auto_paused():
            if self.pause_delay > 0:
                self.add_status("Wait for spindle at speed before resuming", WARNING)
                return
            self.w.btn_pause.setText("  PAUSE")
            self.w.lbl_pgm_color.setStyleSheet(f'Background-color: {RUN_COLOR};')
            self.h['runtime-pause'] = False
            ACTION.PAUSE()
        else:
            self.w.btn_pause.setText("  RESUME")
            self.w.lbl_pgm_color.setStyleSheet(f'Background-color: {PAUSE_COLOR};')
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
        self.h['eoffset-count'] = int(self.w.lineEdit_eoffset_count.text())
        self.h['spindle-inhibit'] = True
        self.add_status(f"Spindle paused at {self.w.lineEdit_runtime.text()}")
        # modify runtime text
        self.runtime_save = self.w.lineEdit_runtime.text()
        self.pause_delay = int(self.w.lineEdit_spindle_delay.text())
        self.w.lineEdit_runtime.setText(f"WAIT {self.pause_delay}")
        self.w.lineEdit_runtime.setStyleSheet("color: red;")
        # instantiate warning box
        icon = QMessageBox.Warning
        title = "SPINDLE PAUSED"
        info = "Wait for spindle at speed signal before resuming"
        button = QMessageBox.Ok
        retval = self.message_box(icon, title, info, button)
        if retval == QMessageBox.Ok:
            self.h['spindle-inhibit'] = False
            # add time delay for spindle to attain speed
            self.pause_timer.start(1000)

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
    def btn_home_all_clicked(self, obj):
        if not STATUS.is_all_homed():
            ACTION.SET_MACHINE_HOMING(-1)
        else:
        # instantiate dialog box
            icon = QMessageBox.Question
            title = "UNHOME ALL AXES"
            info = "Do you want to Unhome all axes?"
            buttons = QMessageBox.Cancel | QMessageBox.Ok
            retval = self.message_box(icon, title, info, buttons)
            if retval == QMessageBox.Ok:
                ACTION.SET_MACHINE_UNHOMED(-1)

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
        ACTION.CALL_MDI("G90")
        if dest == 'zero':
            ACTION.CALL_MDI_WAIT("G53 G0 Z0", 30)
            ACTION.CALL_MDI_WAIT("X0 Y0", 30)
        elif dest == 'home':
            ACTION.CALL_MDI_WAIT("G53 G0 Z0", 30)
            cmd = f"G53 G0 X{self.w.lbl_home_x.text()} Y{self.w.lbl_home_y.text()}"
            ACTION.CALL_MDI_WAIT(cmd, 30)
        elif dest == 'sensor':
            ACTION.CALL_MDI_WAIT("G53 G0 Z0", 30)
            cmd = f"G53 G0 X{self.w.lineEdit_sensor_x.text()} Y{self.w.lineEdit_sensor_y.text()}"
            ACTION.CALL_MDI_WAIT(cmd, 30)
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

    # TOOL tab
    def btn_add_tool_pressed(self):
        if not STATUS.is_on_and_idle():
            self.add_status("Status must be ON and IDLE", WARNING)
            return
        array = [self.next_available, self.next_available, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 'New tool']
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
        TOOL.DELETE_TOOLS(tools)
        self.add_status(f"Deleted tool {tools[0]}")
        self.tool_db.delete_tool(tools[0])
        self.get_next_available()

    def btn_load_tool_pressed(self):
        tool = self.get_checked_tools()
        if len(tool) > 1:
            self.add_status("Select only 1 tool to load", ERROR)
        elif tool:
            ACTION.CALL_MDI(f"M61 Q{tool[0]} G43")
            self.add_status(f"Tool {tool[0]} loaded")
        else:
            self.add_status("No tool selected", WARNING)

    def btn_tool_db_clicked(self, state):
        if not state and self.w.btn_enable_edit.isChecked():
            self.w.btn_enable_edit.setChecked(False)
        self.w.stackedWidget_tools.setCurrentIndex(state)
        self.w.widget_tooltable_btns.setVisible(not state)
        self.w.widget_database_btns.setVisible(state)

    def show_db_help_page(self):
        self.setup_utils.show_help_page(self.db_helpfile)

    # STATUS tab
    def btn_clear_status_clicked(self):
        STATUS.emit('update-machine-log', None, 'DELETE')

    def btn_select_log_pressed(self, state):
        if state:
            self.w.stackedWidget_log.setCurrentIndex(1)
        else:
            self.w.stackedWidget_log.setCurrentIndex(0)
        self.w.widget_status_errors.setVisible(not state)

    def btn_save_log_pressed(self):
        if self.w.btn_select_log.isChecked():
            text = self.w.integrator_log.toPlainText()
            target = "system"
        else:
            text = self.w.machine_log.toPlainText()
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

    def use_mdi_keyboard_changed(self, state):
        self.w.widget_mdi_controls.setVisible(not state)
        self.w.mdihistory.set_soft_keyboard(state)

    def edit_gcode_changed(self, state):
        if state:
            self.w.gcode_viewer.editMode()
        else:
            self.w.gcode_viewer.readOnlyMode()

    def chk_run_from_line_changed(self, state):
        if not state:
            self.w.btn_cycle_start.setText('  CYCLE START')
            self.start_line = 1

    def chk_show_macros_changed(self, state):
        if self.macros_defined == 0: return
        if state and not STATUS.is_auto_mode():
            self.w.group1_macro_buttons.show()
            if self.macros_defined > 10:
                self.w.group2_macro_buttons.show()
                for i in range(self.macros_defined, 20):
                    self.w[f'btn_macro{i}'].setEnabled(False)
            else:
                for i in range(self.macros_defined, 10):
                    self.w[f'btn_macro{i}'].setEnabled(False)
        else:
            self.w.group1_macro_buttons.hide()
            self.w.group2_macro_buttons.hide()

    def touchoff_changed(self, state):
        if not state: return
        image = ''
        if self.w.chk_touchplate.isChecked():
            self.w.btn_touchoff.setText("TOUCHPLATE")
            self.w.btn_touchoff.setToolTip("Auto probe Z down to touchplate")
            image = 'touch_plate.png'
        elif self.w.chk_auto_toolsensor.isChecked():
            self.w.btn_touchoff.setText("AUTO TOUCHOFF Z")
            self.w.btn_touchoff.setToolTip("Auto probe Z down to tool sensor")
            image = 'tool_sensor.png'
        elif self.w.chk_manual_toolsensor.isChecked():
            self.w.btn_touchoff.setText("MANUAL TOUCHOFF Z")
            self.w.btn_touchoff.setToolTip("Set workpiece Z0")
            image = 'tool_gauge.png'
        if image:
            image_file = os.path.join(PATH.CONFIGPATH, 'tool_icons/' + image)
            self.w.lbl_touchoff_image.setPixmap(QtGui.QPixmap(image_file))
        self.w.lineEdit_touch_height.setReadOnly(not self.w.chk_touchplate.isChecked())
        self.w.lineEdit_sensor_height.setReadOnly(not self.w.chk_auto_toolsensor.isChecked())
        self.w.lineEdit_gauge_height.setReadOnly(not self.w.chk_manual_toolsensor.isChecked())

    #####################
    # GENERAL FUNCTIONS #
    #####################
    def tool_data_changed(self, new, old, roles):
        if new.column() > 1: return
        old_list = self.tool_list
        self.get_next_available()
        new_list = self.tool_list
        old_tno = list(set(old_list) - set(new_list))
        new_tno = list(set(new_list) - set(old_list))
        self.tool_db.update_tool_no(old_tno[0], new_tno[0])
        
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
        self.max_spindle_power = float(self.w.lineEdit_max_power.text())
        if self.max_spindle_power <= 0:
            self.max_spindle_power = 100
            self.w.lineEdit_max_power.setText('100')
            self.add_status("Max spindle power must be >0 - using default of 100", WARNING)

    def probe_offset_edited(self):
        x = self.w.lineEdit_probe_x.text()
        y = self.w.lineEdit_probe_y.text()
        self.probe.set_offsets(x, y)

    def show_selected_axis(self, obj):
        if self.w.chk_use_mpg.isChecked():
            self.w.jog_xy.set_highlight('X', bool(self.h['axis-select-x'] is True))
            self.w.jog_xy.set_highlight('Y', bool(self.h['axis-select-y'] is True))
            self.w.jog_az.set_highlight('Z', bool(self.h['axis-select-z'] is True))
            if 'A' in self.axis_list:
                self.w.jog_az.set_highlight('A', bool(self.h['axis-select-a'] is True))

    # class patched function from file_manager widget
    def load_code(self, fname):
        if fname is None: return
        if self.w.PREFS_:
            self.w.PREFS_.putpref('last_loaded_directory', os.path.dirname(fname), str, 'BOOK_KEEPING')
            self.w.PREFS_.putpref('RecentPath_0', fname, str, 'BOOK_KEEPING')
        if fname.endswith(".ngc") or fname.endswith(".py"):
            self.w.cmb_gcode_history.addItem(fname)
            self.w.cmb_gcode_history.setCurrentIndex(self.w.cmb_gcode_history.count() - 1)
            ACTION.OPEN_PROGRAM(fname)
            self.w.main_tab_widget.setCurrentIndex(TAB_MAIN)
            self.w.btn_main.setChecked(True)
        elif fname.endswith(".html"):
            self.setup_utils.show_html(fname)
            self.w.main_tab_widget.setCurrentIndex(TAB_UTILS)
            self.w.btn_utils.setChecked(True)
            self.add_status(f"Loaded HTML file : {fname}")
        elif fname.endswith(".pdf"):
            self.setup_utils.show_pdf(fname)
            self.w.main_tab_widget.setCurrentIndex(TAB_UTILS)
            self.w.btn_utils.setChecked(True)
            self.add_status(f"Loaded PDF file : {fname}")
        else:
            self.add_status("Unknown or invalid filename", WARNING)

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
        self.add_status("Touchoff routine returned success")
            
    def touchoff_error(self, data):
        self.add_status(data, WARNING)
        # if the touchoff routine failed, show a dialog
        icon = QMessageBox.Warning
        title = "Tool Touchoff Failed"
        info = f"Ensure tool tip is within {self.w.lineEdit_max_probe.text()} {self.machine_units} of touchoff device"
        button = QMessageBox.Ok
        retval = self.message_box(icon, title, info, button)

    def spindle_pause_timer(self):
        self.pause_delay -= 1
        if self.pause_delay <= 0:
            self.h['eoffset-count'] = 0.0
            self.add_status("Program resumed")
            self.w.lineEdit_runtime.setText(self.runtime_save)
            self.w.lineEdit_runtime.setStyleSheet(f"color; {self.runtime_color.name()};")
        else:
            self.w.lineEdit_runtime.setText(f"WAIT {self.pause_delay}")
            self.pause_timer.start(1000)
        
    def kb_jog(self, state, axis, direction):
        if not STATUS.is_man_mode() or not STATUS.machine_is_on():
            self.add_status('Machine must be ON and in Manual mode to jog', WARNING)
            return
        if state == 0: direction = 0
        ACTION.DO_JOG(axis, direction)

    def add_status(self, message, level=DEFAULT):
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
            self.w.statusbar.setStyleSheet(f"color: {self.statusbar_color};")
            self.w.statusbar.showMessage(message)
        if not message == "":
            STATUS.emit('update-machine-log', message, 'TIME')

    def statusbar_changed(self, message):
        if message == "":
            self.w.statusbar.setStyleSheet(f"color: {self.statusbar_color};")

    def enable_auto(self, state):
        if not STATUS.machine_is_on(): return
        if self.zlevel is not None:
            self.w.btn_enable_comp.setEnabled(not state)
        self.w.btn_pause_spindle.setEnabled(not state)
        self.w.btn_goto_sensor.setEnabled(not state)
        self.w.groupBox_jog_pads.setEnabled(not state)
        self.w.btn_cycle_start.setEnabled(state)
        self.w.lineEdit_eoffset_count.setReadOnly(state)
        if self.w.chk_show_macros.isChecked():
            self.chk_show_macros_changed(not state)
        if state:
            self.w.btn_main.setChecked(True)
            self.w.main_tab_widget.setCurrentIndex(TAB_MAIN)
            self.w.widget_gcode_history.hide()
            self.w.btn_edit_gcode.setChecked(False)
            self.w.gcode_viewer.readOnlyMode()
        else:
            self.w.widget_gcode_history.show()
        if STATUS.is_mdi_mode():
            self.w.stackedWidget_gcode.setCurrentIndex(1)
        else:
            self.w.stackedWidget_gcode.setCurrentIndex(0)

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
            self.w.btn_cycle_start.setText(f"  CYCLE START\n  LINE {self.start_line}")
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
        if not self.feedrate_color is None:
            self.w.lbl_feedrate.setStyleSheet(f"color: {self.feedrate_color.name()};")
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

    def message_box(self, icon, title, info, buttons):
        msg = QMessageBox()
        msg.setIcon(icon)
        msg.setWindowTitle(title)
        msg.setText(info)
        msg.setStandardButtons(buttons)
        return msg.exec_()

    #####################
    # KEY BINDING CALLS #
    #####################

    def on_keycall_ESTOP(self,event,state,shift,cntrl):
        if state:
            ACTION.SET_ESTOP_STATE(True)

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
        if state and STATUS.is_auto_mode() and self.use_keyboard():
            self.pause_program()

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

    #################################
    # Check for updates from Github #
    #################################
    def check_for_updates(self):
        if not self.w.chk_for_update.isChecked(): return
        if not self.connection_available(): return
        self.add_status("Checking github for updated QtDragon")
        owner = "persei802"
        repo = "Qtdragon_hd"
        remote_version = self.get_remote_version(owner, repo)
        if remote_version is None:
            self.add_status("Remote request returned invalid response", WARNING)
            return
        if remote_version == VERSION:
            self.add_status(f"This is the latest version ({VERSION}) of Qtdragon_hd")
        else:
            self.add_status(f"There is a new version ({remote_version}) available")

    def get_remote_version(self, owner, repo):
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/master/qtdragon/qtdragon_handler.py"
        response = requests.get(url)
        version = None
        if response.status_code == 200:
            data = response.text
            lines = data.split('\n')
            for line in lines:
                if 'VERSION' in line:
                    version = line.split('=')[1]
                    version = version.strip(' ')
                    version = version.strip("'")
                    break
        return version

    def connection_available(self, url="https://www.github.com", timeout=3):
        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code == 200:
                return True
            else:
                self.add_status("Received response but not OK status", WARNING)
                return False
        except requests.ConnectionError:
            self.add_status("No internet connection", ERROR)
            return False
        except requests.Timeout:
            self.add_status("Connection timed out", ERROR)
            return False

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
