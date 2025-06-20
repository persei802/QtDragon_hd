#!/usr/bin/env python3
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
import numpy as np
import tempfile
import atexit

from PyQt5 import QtCore, QtGui, QtWidgets, uic
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFileDialog, QWidget

from qtvcp.core import Info, Status, Action, Path, Tool
from qtvcp import logger

from lib.preview import Preview
from lib.event_filter import EventFilter

LOG = logger.getLogger(__name__)
LOG.setLevel(logger.INFO) # One of DEBUG, INFO, WARNING, ERROR, CRITICAL
INFO = Info()
STATUS = Status()
ACTION = Action()
PATH = Path()
TOOL = Tool()
HERE = os.path.dirname(os.path.abspath(__file__))
HELP = os.path.join(PATH.CONFIGPATH, "help_files")
IMAGES = os.path.join(PATH.CONFIGPATH, 'qtdragon/images')
WARNING = 1


class Facing(QWidget):
    def __init__(self, parent=None):
        super(Facing, self).__init__()
        self.parent = parent
        self.tool_db = self.parent.tool_db
        self.h = self.parent.parent
        self.calculate_pass = None
        self.helpfile = 'facing_help.html'
        self.dialog_code = 'CALCULATOR'
        self.kbd_code = 'KEYBOARD'
        self.tool_code = 'TOOLCHOOSER'
        self.default_style = ''
        self.tmpl = '.3f' if INFO.MACHINE_IS_METRIC else '.4f'
        # Load the widgets UI file:
        self.filename = os.path.join(HERE, 'facing.ui')
        try:
            self.instance = uic.loadUi(self.filename, self)
        except AttributeError as e:
            self.h.add_status(e, WARNING)

        # Initial values
        self.rpm = INFO.get_error_safe_setting("DISPLAY", "DEFAULT_SPINDLE_0_SPEED", 500)
        self.min_x = INFO.get_safe_float("AXIS_X", "MIN_LIMIT")
        self.max_x = INFO.get_safe_float("AXIS_X", "MAX_LIMIT")
        self.min_y = INFO.get_safe_float("AXIS_Y", "MIN_LIMIT")
        self.max_y = INFO.get_safe_float("AXIS_Y", "MAX_LIMIT")
        self.min_rpm = INFO.get_safe_int("DISPLAY", "MIN_SPINDLE_0_SPEED")
        self.max_rpm = INFO.get_safe_int("DISPLAY", "MAX_SPINDLE_0_SPEED")
        self.max_feed = INFO.get_safe_int("DISPLAY", "MAX_LINEAR_VELOCITY") * 60
        self.size_x = 0.0
        self.size_y = 0.0
        self.tool = 0
        self.xy_feedrate = 0
        self.z_feedrate = 0
        self.stepover = 0.0
        self.tool_dia = 0.0
        self.safe_z = 0.0
        self.stepdown = 0.0
        self.zlevel = 0.0
        self.zfinal = 0.0
        self.valid = True
        self.red_border = "border: 2px solid red;"
        self.parm_list = ["size_x", "size_y", "tool_diameter", "spindle", "xy_feedrate", "z_feedrate",
                          "stepover", "safe_z", "start_z", "last_z", "stepdown"]
        self.preview = Preview()
        self.layout_preview.addWidget(self.preview)

        # set valid input formats for lineEdits
        self.lineEdit_tool_num.setValidator(QtGui.QIntValidator(1, 99))
        self.lineEdit_tool_diameter.setValidator(QtGui.QDoubleValidator(0, 999, 3))
        self.lineEdit_spindle.setValidator(QtGui.QIntValidator(0, 99999))
        self.lineEdit_xy_feedrate.setValidator(QtGui.QIntValidator(0, 9999))
        self.lineEdit_z_feedrate.setValidator(QtGui.QIntValidator(0, 9999))
        self.lineEdit_safe_z.setValidator(QtGui.QDoubleValidator(0, 9999, 3))
        self.lineEdit_start_z.setValidator(QtGui.QDoubleValidator(-9999, 9999, 3))
        self.lineEdit_last_z.setValidator(QtGui.QDoubleValidator(-9999, 9999, 3))
        self.lineEdit_stepover.setValidator(QtGui.QDoubleValidator(0, 99, 3))
        self.lineEdit_stepdown.setValidator(QtGui.QDoubleValidator(0, 99, 3))
        self.lineEdit_size_x.setValidator(QtGui.QDoubleValidator(0, 9999, 3))
        self.lineEdit_size_y.setValidator(QtGui.QDoubleValidator(0, 9999, 3))

        # setup event filter to catch focus_in events
        self.event_filter = EventFilter(self)
        for line in self.parm_list:
            self[f'lineEdit_{line}'].installEventFilter(self.event_filter)
        self.lineEdit_tool_num.installEventFilter(self.event_filter)
        self.lineEdit_comment.installEventFilter(self.event_filter)
        self.event_filter.set_line_list(self.parm_list)
        self.event_filter.set_kbd_list('comment')
        self.event_filter.set_tool_list('tool_num')
        self.event_filter.set_parms(('_facing_', True))

        # signal connections
        self.chk_units.stateChanged.connect(lambda state: self.units_changed(state))
        self.chk_use_calc.stateChanged.connect(lambda state: self.event_filter.set_dialog_mode(state))
        self.lineEdit_tool_num.editingFinished.connect(self.load_tool)
        self.btn_preview.pressed.connect(self.preview_program)
        self.btn_create.pressed.connect(self.create_program)
        self.btn_send.pressed.connect(self.send_program)
        self.btn_help.pressed.connect(self.show_help)

    def _hal_init(self):
        def homed_on_status():
            return (STATUS.machine_is_on() and (STATUS.is_all_homed() or INFO.NO_HOME_REQUIRED))
        STATUS.connect('general', self.dialog_return)
        STATUS.connect('state_off', lambda w: self.setEnabled(False))
        STATUS.connect('state_estop', lambda w: self.setEnabled(False))
        STATUS.connect('interp-idle', lambda w: self.setEnabled(homed_on_status()))
        STATUS.connect('all-homed', lambda w: self.setEnabled(True))
        self.default_style = self.lineEdit_tool_num.styleSheet()
        self.chk_units.setChecked(True)

    def dialog_return(self, w, message):
        rtn = message['RETURN']
        name = message.get('NAME')
        obj = message.get('OBJECT')
        code = bool(message.get('ID') == '_facing_')
        next = message.get('NEXT', False)
        back = message.get('BACK', False)
        if code and name == self.dialog_code:
            obj.setStyleSheet(self.default_style)
            if rtn is not None:
                if obj.objectName().replace('lineEdit_', '') in ['spindle', 'xy_feedrate', 'z_feedrate']:
                    obj.setText(str(int(rtn)))
                else:
                    obj.setText(f'{rtn:{self.tmpl}}')
            # request for next input widget from linelist
            if next:
                newobj = self.event_filter.findNext()
                self.event_filter.show_calc(newobj, True)
            elif back:
                newobj = self.event_filter.findBack()
                self.event_filter.show_calc(newobj, True)
        elif code and name == self.kbd_code:
            obj.setStyleSheet(self.default_style)
            if rtn is not None:
                obj.setText(rtn)
        elif code and name == self.tool_code:
            obj.setStyleSheet(self.default_style)
            if rtn is not None:
                obj.setText(str(int(rtn)))
                self.load_tool()
        elif code and name == 'SAVE':
            if rtn is None: return
            if self.calculate_program(rtn):
                self.h.add_status(f"Program successfully saved to {rtn}")
            else:
                self.h.add_status("Could not calculate program toolpath", WARNING)

    def units_changed(self, state):
        text = "MM" if state else "IN"
        chk_text = 'METRIC' if state else 'IMPERIAL'
        self.chk_units.setText(chk_text)
        self.lbl_feed_unit.setText(text + "/MIN")
        self.lbl_tool_unit.setText(text)
        self.lbl_safe_z_unit.setText(text)
        self.lbl_z_unit.setText(text)
        self.lbl_stepover_unit.setText(text)
        self.lbl_stepdown_unit.setText(text)
        self.lbl_size_unit.setText(text)

    def validate(self):
        valid = True
        blank = "Input field cannot be blank"
        for item in self.parm_list:
            self['lineEdit_' + item].setStyleSheet(self.default_style)
        # check tool number
        try:
            self.tool = int(self.lineEdit_tool_num.text())
            if self.tool <= 0:
                self.lineEdit_tool_num.setStyleSheet(self.red_border)
                self.h.add_status("Error - Tool Number must be > 0", WARNING)
                valid = False
        except:
            self.lineEdit_tool_num.setStyleSheet(self.red_border)
            valid = False
        # check for valid size
        try:
            self.size_x = float(self.lineEdit_size_x.text())
            self.size_y = float(self.lineEdit_size_y.text())
            if self.size_x > (self.max_x - self.min_x):
                self.h.add_status("X size greater than limits", WARNING)
                self.lineEdit_size_x.setStyleSheet(self.red_border)
                valid = False
            if self.size_y > (self.max_y - self.min_y):
                self.h.add_status("Y size greater than limits", WARNING)
                self.lineEdit_size_y.setStyleSheet(self.red_border)
                valid = False
        except:
            self.h.add_status(blank, WARNING)
            self.lineEdit_size_x.setStyleSheet(self.red_border)
            self.lineEdit_size_y.setStyleSheet(self.red_border)
            valid = False
        # check for valid spindle rpm
        try:
            self.rpm = int(self.lineEdit_spindle.text())
            if self.rpm < self.min_rpm or self.rpm > self.max_rpm:
                self.h.add_status(f"Spindle RPM must be between {self.min_rpm} and {self.max_rpm}", WARNING)
                self.lineEdit_spindle.setStyleSheet(self.red_border)
                valid = False
        except:
            self.h.add_status(blank, WARNING)
            self.lineEdit_spindle.setStyleSheet(self.red_border)
            valid = False
        # check for valid xy feedrate
        try:
            self.xy_feedrate = float(self.lineEdit_xy_feedrate.text())
            if self.xy_feedrate <= 0 or self.xy_feedrate > self.max_feed:
                self.h.add_status(f"XY Feedrate must be > 0 and < {self.max_feed}", WARNING)
                self.lineEdit_xy_feedrate.setStyleSheet(self.red_border)
                valid = False
        except:
            self.h.add_status(blank, WARNING)
            self.lineEdit_xy_feedrate.setStyleSheet(self.red_border)
            valid = False
        # check for valid z feedrate
        try:
            self.z_feedrate = float(self.lineEdit_z_feedrate.text())
            if self.z_feedrate <= 0 or self.z_feedrate > self.max_feed:
                self.h.add_status(f"Z Feedrate must be > 0 and < {self.max_feed}", WARNING)
                self.lineEdit_z_feedrate.setStyleSheet(self.red_border)
                valid = False
        except:
            self.h.add_status(blank, WARNING)
            self.lineEdit_z_feedrate.setStyleSheet(self.red_border)
            valid = False
        # check for valid safe_z level
        try:
            self.safe_z = float(self.lineEdit_safe_z.text())
            if self.safe_z <= 0.0:
                self.h.add_status("Safe Z height should be > 0", WARNING)
                self.lineEdit_safe_z.setStyleSheet(self.red_border)
                valid = False
        except:
            self.h.add_status(blank, WARNING)
            self.lineEdit_safe_z.setStyleSheet(self.red_border)
            valid = False
        # check for valid tool diameter
        try:
            self.tool_dia = float(self.lineEdit_tool_diameter.text())
            if self.tool_dia <= 0.0:
                self.h.add_status("Tool diameter must be > 0", WARNING)
                self.lineEdit_tool_diameter.setStyleSheet(self.red_border)
                valid = False
        except:
            self.h.add_status(blank, WARNING)
            self.lineEdit_tool_diameter.setStyleSheet(self.red_border)
            valid = False
        # check for valid stepover
        try:
            self.stepover = float(self.lineEdit_stepover.text())
            if self.stepover == 0 \
            or self.stepover > self.tool_dia \
            or (self.stepover * 2) > min(self.size_x, self.size_y):
                self.h.add_status("Stepover should be > 0 and < tool diameter", WARNING)
                self.lineEdit_stepover.setStyleSheet(self.red_border)
                valid = False
        except:
            self.h.add_status(blank, WARNING)
            self.lineEdit_stepover.setStyleSheet(self.red_border)
            valid = False
        # check for valid stepdown
        try:
            self.stepdown = float(self.lineEdit_stepdown.text())
            if self.stepdown <= 0:
                self.h.add_status("Stepdown must be > 0 even if using only 1 pass", WARNING)
                self.lineEdit_stepdown.setStyleSheet(self.red_border)
                valid = False
        except:
            self.h.add_status(blank, WARNING)
            self.lineEdit_stepdown.setStyleSheet(self.red_border)
            valid = False
        # check for first and last z levels
        try:
            self.zlevel = float(self.lineEdit_start_z.text())
            self.zfinal = float(self.lineEdit_last_z.text())
            if self.zfinal > self.zlevel:
                self.h.add_status("Final Z level must be <= start Z level", WARNING)
                self.lineEdit_last_z.setStyleSheet(self.red_border)
                valid = False
        except:
            self.h.add_status(blank, WARNING)
            self.lineEdit_last_z.setStyleSheet(self.red_border)
            valid = False
        return valid

    def load_tool(self):
        #check for valid tool and populate rpm, dia and feed parameters
        try:
            self.tool = int(self.lineEdit_tool_num.text())
        except:
            self.tool = 0
        if self.tool > 0:
            info = TOOL.GET_TOOL_INFO(self.tool)
            dia = info[11]
            self.lineEdit_tool_diameter.setText(f"{dia:8.3f}")
            rpm = self.tool_db.get_tool_data(self.tool, "RPM")
            self.lineEdit_spindle.setText(str(rpm))
            feed = self.tool_db.get_tool_data(self.tool, "FEED")
            self.lineEdit_xy_feedrate.setText(str(feed))
            self.lineEdit_tool_num.setStyleSheet(self.default_style)
            ACTION.CALL_MDI(f"M61 Q{self.tool}")
        else:
            self.h.add_status("Invalid tool number specified", WARNING)
            self.lineEdit_tool_num.setStyleSheet(self.red_border)
        self.validate()

    def preview_program(self):
        if not self.validate(): return
        filename = self.make_temp()
        if not self.calculate_program(filename):
            self.h.add_status("Could not calculate program toolpath", WARNING)
            return
        try:
            result = self.preview.load_program(filename)
            if result:
                self.preview.set_path_points()
                self.preview.update()
                self.h.add_status(f'Previewing file {filename}')
            else:
                self.h.add_status('Program preview failed', WARNING)
        except Exception as e:
            self.h.add_status(f'Error loading program - {e}', WARNING)

    def create_program(self):
        if not self.validate(): return
        mess = {'NAME': 'SAVE',
                'ID': '_facing_',
                'TITLE': 'Save Program as',
                'FILENAME': '',
                'EXTENSIONS': 'Gcode Files (*.ngc *.nc);;',
                'GEONAME': '__file_save',
                'OVERLAY': False}
        LOG.debug(f'message sent:{mess}')
        ACTION.CALL_DIALOG(mess)

    def send_program(self):
        if not self.validate(): return
        filename = self.make_temp()
        if self.calculate_program(filename):
            ACTION.OPEN_PROGRAM(filename)
            self.h.add_status("Program successfully sent to Linuxcnc")
        else:
            self.h.add_status("Could not calculate program toolpath", WARNING)

    def calculate_program(self, fname):
        passes = 0
        comment = self.lineEdit_comment.text()
        unit_code = 'G21' if self.chk_units.isChecked() else 'G20'
        units_text = 'Metric' if self.chk_units.isChecked() else 'Imperial'
        self.line_num = 5
        self.file = open(fname, 'w')
        # opening preamble
        self.file.write("%\n")
        self.file.write(f"({comment})\n")
        self.file.write(f"(**NOTE - All units are {units_text})\n")
        self.file.write(f"(Area: X {self.size_x} by Y {self.size_y})\n")
        self.file.write(f"({self.tool_dia} Tool Diameter with {self.stepover} Stepover)\n")
        self.file.write("\n")
        self.next_line(f"G40 G49 G64 P0.03 M6 T{self.tool}")
        self.next_line("G17")
        self.next_line(unit_code)
        if self.chk_mist.isChecked():
            self.next_line("M7")
        if self.chk_flood.isChecked():
            self.next_line("M8")
        self.next_line(f"S{self.rpm} M3")
        if self.rbtn_raster_0.isChecked():
            self.calculate_pass = self.raster_0
        elif self.rbtn_raster_45.isChecked():
            self.calculate_pass = self.raster_45
        elif self.rbtn_raster_90.isChecked():
            self.calculate_pass = self.raster_90
        else:
            self.file.write("(Unable to determine raster direction)\n")
            return False
        last_pass = False
        # start facing passes
        while True:
            passes += 1
            self.file.write(f"(Pass {passes})\n")
            if self.zlevel <= self.zfinal:
                self.zlevel = self.zfinal
                last_pass = True
            self.next_line(f"G0 Z{self.safe_z}")
            self.next_line("G0 X0.0 Y0.0")
            self.next_line(f"G1 Z{self.zlevel} F{self.z_feedrate}")
            self.calculate_pass()
            if last_pass is True: break
            self.zlevel -= self.stepdown
        # final profile
        if self.chk_profile.isChecked():
            self.file.write("(Profile pass)\n")
            self.next_line(f"G0 Z{self.safe_z}")
            self.next_line("G0 X0.0 Y0.0")
            self.next_line(f"G1 Z{self.zfinal} F{self.z_feedrate}")
            self.next_line(f"G1 X{self.size_x} F{self.xy_feedrate}")
            self.next_line(f"G1 Y{self.size_y}")
            self.next_line("G1 X0")
            self.next_line("G1 Y0")
        # closing section
        self.next_line(f"G0 Z{self.safe_z}")
        self.next_line("M9")
        self.next_line("M5")
        self.next_line("M2")
        self.file.write("%\n")
        self.file.close()
        return True

    def raster_0(self):
        i = 1
        x = (0.0, self.size_x)
        next_x = self.size_x
        next_y = 0.0
        self.next_line(f"G1 X{next_x} F{self.xy_feedrate}")
        while next_y < self.size_y:
            i ^= 1
            next_x = x[i]
            next_y = min(next_y + self.stepover, self.size_y)
            self.next_line(f"Y{next_y}")
            self.next_line(f"X{next_x}")

    def raster_45(self):
        # calculate coordinate arrays
        ysteps = int(self.size_y // self.stepover)
        xsteps = int(self.size_x // self.stepover)
        left = np.empty(shape=(ysteps,2), dtype=float)
        right = np.empty(shape=(ysteps,2), dtype=float)
        bottom = np.empty(shape=(xsteps,2), dtype=float)
        top = np.empty(shape=(xsteps,2), dtype=float)
        ycoord = self.stepover
        for i in range(ysteps):
            left[i][0] = 0.0
            left[i][1] = ycoord
            ycoord += self.stepover
        xcoord = ycoord - self.size_y
        for i in range(xsteps):
            top[i][0] = xcoord
            top[i][1] = self.size_y
            xcoord += self.stepover
        xcoord = self.stepover
        for i in range(xsteps):
            bottom[i][0] = xcoord
            bottom[i][1] = 0.0
            xcoord += self.stepover
        ycoord = xcoord - self.size_x
        for i in range(ysteps):
            right[i][0] = self.size_x
            right[i][1] = ycoord
            ycoord += self.stepover
        # concatenate (left, top) and (bottom, right)
        array1 = np.concatenate((left, top))
        array2 = np.concatenate((bottom, right))
        # move to start position
        self.next_line(f"G1 Y{array1[0][1]} F{self.xy_feedrate}")
        i = 0
        # calculate toolpath
        while 1:
            self.next_line(f"X{array2[i][0]} Y{array2[i][1]}")
            if array2[i][1] == 0.0: # bottom row
                if array2[i][0] == self.size_x: # bottom right corner
                    self.next_line(f"Y{self.stepover}")
                elif (array2[i][0] + self.stepover) <= self.size_x:
                    self.next_line(f"G91 X{self.stepover}")
                    self.next_line("G90")
                else:
                    self.next_line(f"X{self.size_x}")
                    self.next_line(f"Y{right[0][1]}")
            elif array2[i][0] == self.size_x: # right side
                if (array2[i][1] + self.stepover) <= self.size_y:
                    self.next_line(f"G91 Y{self.stepover}")
                    self.next_line("G90")
                else:
                    self.next_line(f"Y{self.size_y}")
            else:
                self.h.add_status("FATAL ERROR in Raster_45", WARNING)
                return
            i += 1
            if i == len(array1 + 1): break
            self.next_line(f"X{array1[i][0]} Y{array1[i][1]}")
            if array1[i][0] == 0.0: # left side
                if array1[i][1] == self.size_y: # top left corner
                    self.next_line(f"X{self.stepover}")
                elif (array1[i][1] + self.stepover) <= self.size_y:
                    self.next_line(f"G91 Y{self.stepover}")
                    self.next_line("G90")
                else:
                    self.next_line(f"Y{self.size_y}")
                    self.next_line(f"X{top[0][0]}")
            elif array1[i][1] == self.size_y: # top row
                if (array1[i][0] + self.stepover) <= self.size_x:
                    self.next_line(f"G91 X{self.stepover}")
                    self.next_line("G90")
                else:
                    self.next_line(f"X{self.size_x}")
            else:
                self.h.add_status("FATAL ERROR", WARNING)
                return
            i += 1
            if i == len(array1): break

    def raster_90(self):
        i = 1
        y = (0.0, self.size_y)
        next_x = 0.0
        next_y = self.size_y
        self.next_line(f"G1 Y{next_y} F{self.xy_feedrate}")
        while next_x < self.size_x:
            i ^= 1
            next_y = y[i]
            next_x = min(next_x + self.stepover, self.size_x)
            self.next_line(f"X{next_x}")
            self.next_line(f"Y{next_y}")

    def next_line(self, text):
        self.file.write(f"N{self.line_num} " + text + "\n")
        self.line_num += 5

    def show_help(self):
        fname = os.path.join(HELP, self.helpfile)
        self.parent.show_help_page(fname)

    def make_temp(self):
        fd, path = tempfile.mkstemp(prefix='facing', suffix='.ngc')
        atexit.register(lambda: os.remove(path))
        return path

    # required code for subscriptable objects
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)
