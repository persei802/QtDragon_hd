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

from PyQt5 import uic
from PyQt5.QtGui import QIntValidator, QDoubleValidator
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget

from qtvcp.core import Info, Status, Action, Path, Tool
from qtvcp import logger

from lib.preview import Preview
from lib.event_filter import EventFilter

from utils.utils_mixin import Common

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


class Facing(QWidget, Common):
    def __init__(self, parent=None):
        super(Facing, self).__init__()
        self.parent = parent
        self.h = self.parent.parent
        self.calculate_pass = None
        self.helpfile = 'facing_help.html'
        self.default_style = ''
        self.geometry = None
        self.tmpl = '.3f' if INFO.MACHINE_IS_METRIC else '.4f'
        # Load the widgets UI file:
        self.filename = os.path.join(HERE, 'facing.ui')
        try:
            self.instance = uic.loadUi(self.filename, self)
        except AttributeError as e:
            self.h.add_status(e, WARNING)

        self.float_inputs = ['diameter', 'size_x', 'size_y', 'stepover', 'stepdown', 'safe_z', 'start_z', 'last_z']
        self.int_inputs = ['tool', 'xy_feedrate', 'z_feedrate', 'spindle']

        self.preview = Preview()
        self.layout_preview.addWidget(self.preview)

        # set valid input formats for lineEdits
        self.lineEdit_tool.setValidator(QIntValidator(1, 99))
        self.lineEdit_diameter.setValidator(QDoubleValidator(0, 999, 3))
        self.lineEdit_spindle.setValidator(QIntValidator(0, 99999))
        self.lineEdit_xy_feedrate.setValidator(QIntValidator(0, 9999))
        self.lineEdit_z_feedrate.setValidator(QIntValidator(0, 9999))
        self.lineEdit_safe_z.setValidator(QDoubleValidator(0, 9999, 3))
        self.lineEdit_start_z.setValidator(QDoubleValidator(-9999, 9999, 3))
        self.lineEdit_last_z.setValidator(QDoubleValidator(-9999, 9999, 3))
        self.lineEdit_stepover.setValidator(QDoubleValidator(0, 99, 3))
        self.lineEdit_stepdown.setValidator(QDoubleValidator(0, 99, 3))
        self.lineEdit_size_x.setValidator(QDoubleValidator(0, 9999, 3))
        self.lineEdit_size_y.setValidator(QDoubleValidator(0, 9999, 3))

        # setup event filters to catch focus_in events
        self.event_filter = EventFilter(self)
        parm_list = []
        for val in self.float_inputs:
            parm_list.append(val)
            self[f'lineEdit_{val}'].installEventFilter(self.event_filter)
        for val in self.int_inputs:
            parm_list.append(val)
            self[f'lineEdit_{val}'].installEventFilter(self.event_filter)
        self.lineEdit_comment.installEventFilter(self.event_filter)
        self.event_filter.set_line_list(parm_list)
        self.event_filter.set_kbd_list('comment')
        self.event_filter.set_tool_list('tool')
        self.event_filter.set_parms(('_facing_', True))

        # signal connections
        self.chk_use_calc.stateChanged.connect(lambda state: self.event_filter.set_dialog_mode(state))
        self.lineEdit_tool.editingFinished.connect(self.load_tool)
        self.btn_save.pressed.connect(self.save_program)
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
        self.default_style = self.lineEdit_tool.styleSheet()

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
                self.load_tool(rtn)

    def set_unit_labels(self):
        unit = "MM" if state else "IN"
        self.lbl_feed_xy_unit.setText(unit + "/MIN")
        self.lbl_feed_z_unit.setText(unit + "/MIN")
        for val in ['diameter', 'safe_z', 'first', 'last', 'stepover', 'stepdown', 'size']:
            self[f'lbl_{val}_unit'].setText(unit)

    def validate(self):
        if not self.check_float_blanks(self.float_inputs): return False
        if not self.check_int_blanks(self.int_inputs): return False
        # additional checks
        for val in self.float_inputs[:-2]:
            if self[val] <= 0.0:
                self[f'lineEdit_{val}'].setStyleSheet(self.red_border)
                self.h.add_status(f'{val} must be > 0', WARNING)
                return False
        for val in ['xy_feedrate', 'z_feedrate']:
            if self[val] <= 0:
                self[f'lineEdit_{val}'].setStyleSheet(self.red_border)
                self.h.add_status(f'{val} must be > 0', WARNING)
                return False
        if self.xy_feedrate > self.max_feed:
            self.lineEdit_xy_feed.setStyleSheet(self.red_border)
            self.h.add_status(f'Feedrate must be less than {self.max_feed}', WARNING)
            return False
        if self.last_z > self.start_z:
            self.lineEdit_last_z.setStyleSheet(self.red_border)
            self.h.add_status('Start height must be greater than last height', WARNING)
            return False
        if self.stepover > self.diameter:
            self.lineEdit_stepover.setStyleSheet(self.red_border)
            self.h.add_status('Stepover must be less than tool diameter', WARNING)
            return False
        if not (self.min_rpm <= self.spindle <= self.max_rpm):
            self.lineEdit_spindle.setStyleSheet(self.red_border)
            self.h.add_status(f'Spindle RPM must be between {self.min_rpm} and {self.max_rpm}', WARNING)
            return False
        return True

    def preview_program(self, filename):
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

    def save_program(self):
        if not self.validate(): return
        if not self.calculate_program():
            self.h.add_status('Unable to calculate program', ERROR)
            return
        caption = 'Save Facing Program'
        _dir = os.path.expanduser('~/linuxcnc/nc_files')
        _filter = 'ngc Files (*.ngc)'
        fileName, _ = self.save_program_file(self, caption, _dir, _filter)
        if fileName:
            if self.gcode:
                with open(fileName, 'w') as f:
                    f.write('\n'.join(self.gcode))
                self.preview_program(fileName)
                self.h.add_status(f"Program saved to {fileName}")
            else:
                self.h.add_status("No gcode data to save", WARNING)
        else:
            self.h.add_status("Program save cancelled")

    def send_program(self):
        if not self.validate(): return
        if not self.calculate_program():
            self.h.add_status('Unable to calculate program', ERROR)
            return
        filename = self.make_temp('facing')
        with open(filename, 'w') as f:
            f.write('\n'.join(self.gcode))
        self.preview_program(filename)
        ACTION.OPEN_PROGRAM(filename)
        self.h.add_status("Program sent to Linuxcnc")

    def load_tool(self, tool=None):
        if tool is None:
            tool = int(self.lineEdit_tool.text())
        info = TOOL.GET_TOOL_INFO(tool)
        if info:
            self.lineEdit_diameter.setText(str(info[11]))
            self.lineEdit_tool_info.setText(info[15])

    def calculate_program(self):
        self.gcode = []
        passes = 0
        comment = self.lineEdit_comment.text()
        unit_code = 'G21' if INFO.MACHINE_IS_METRIC else 'G20'
        units_text = 'Metric' if INFO.MACHINE_IS_METRIC else 'Imperial'
        self.line_num = 5
        # opening preamble
        self.gcode.append("%")
        self.gcode.append(f"({comment})")
        self.gcode.append(f"(**NOTE - All units are {units_text})")
        self.gcode.append(f"(Area: X {self.size_x} by Y {self.size_y})")
        self.gcode.append(f"(Tool Diameter {self.diameter} with Stepover {self.stepover})\n")
        self.next_line(f"G40 G49 G64 P0.03 M6 T{self.tool}")
        self.next_line("G17")
        self.next_line(unit_code)
        if self.chk_mist.isChecked():
            self.next_line("M7")
        if self.chk_flood.isChecked():
            self.next_line("M8")
        self.next_line(f"S{self.spindle} M3")
        if self.rbtn_raster_0.isChecked():
            self.calculate_pass = self.raster_0
        elif self.rbtn_raster_45.isChecked():
            self.calculate_pass = self.raster_45
        elif self.rbtn_raster_90.isChecked():
            self.calculate_pass = self.raster_90
        else:
            self.gcode.append("(Unable to determine raster direction)")
            return False
        zlevel = self.start_z
        last_pass = False
        # start facing passes
        while True:
            passes += 1
            self.gcode.append(f"(Pass {passes})")
            if zlevel <= self.last_z:
                zlevel = self.last_z
                last_pass = True
            self.next_line(f"G0 Z{self.safe_z}")
            self.next_line("G0 X0.0 Y0.0")
            self.next_line(f"G1 Z{zlevel:.3f} F{self.z_feedrate}")
            self.calculate_pass()
            if last_pass is True: break
            zlevel -= self.stepdown
        # final profile
        if self.chk_profile.isChecked():
            self.gcode.append("(Profile pass)")
            self.next_line(f"G0 Z{self.safe_z}")
            self.next_line("G0 X0.0 Y0.0")
            self.next_line(f"G1 Z{self.last_z} F{self.z_feedrate}")
            self.next_line(f"G1 X{self.size_x} F{self.xy_feedrate}")
            self.next_line(f"G1 Y{self.size_y}")
            self.next_line("G1 X0")
            self.next_line("G1 Y0")
        # closing section
        self.post_amble()
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
        self.gcode.append(f"N{self.line_num} {text}")
        self.line_num += 5

    def show_help(self):
        fname = os.path.join(HELP, self.helpfile)
        self.parent.show_help_page(fname)

    # required code for subscriptable objects
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)
