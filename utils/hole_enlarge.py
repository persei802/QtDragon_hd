#!/usr/bin/env python3
# Copyright (c) 2023 Jim Sloot (persei802@gmail.com)
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
from PyQt5 import uic
from PyQt5.QtGui import QIntValidator, QDoubleValidator
from PyQt5.QtWidgets import QFileDialog, QLineEdit, QWidget
from qtvcp.core import Info, Status, Action, Tool, Path
from lib.preview import Preview
from lib.event_filter import EventFilter
from utils.utils_mixin import Common

INFO = Info()
PATH = Path()
TOOL = Tool()
STATUS = Status()
ACTION = Action()
HERE = os.path.dirname(os.path.abspath(__file__))
HELP = os.path.join(PATH.CONFIGPATH, "help_files")
WARNING = 1
ERROR = 2

class Hole_Enlarge(QWidget, Common):
    def __init__(self, parent=None):
        super(Hole_Enlarge, self).__init__()
        self.parent = parent
        self.h = self.parent.parent
        self.helpfile = 'hole_enlarge_help.html'
        self.geometry = None
        self.tmpl = '.3f' if INFO.MACHINE_IS_METRIC else '.4f'
        self.unit_text = ""
        self.angle_inc = 4
        self.line_num = 0
        self.preview = Preview()

        # Load the widgets UI file:
        self.filename = os.path.join(HERE, 'hole_enlarge.ui')
        try:
            self.instance = uic.loadUi(self.filename, self)
        except AttributeError as e:
            print("Error: ", e)

        self.float_inputs = ['tool_dia', 'start_dia', 'final_dia', 'cut_depth', 'safe_z']
        self.int_inputs = ['tool', 'spindle', 'feed', 'loops']

        self.set_unit_labels()

        self.layout_preview.addWidget(self.preview)
        self.lineEdit_tool.setValidator(QIntValidator(1, 9999))
        self.lineEdit_spindle.setValidator(QIntValidator(0, 99999))
        self.lineEdit_feed.setValidator(QIntValidator(0, 9999))
        self.lineEdit_tool_dia.setValidator(QDoubleValidator(0, 99.9, 3))
        self.lineEdit_start_dia.setValidator(QDoubleValidator(0.0, 999.9, 3))
        self.lineEdit_final_dia.setValidator(QDoubleValidator(0.0, 999.9, 3))
        self.lineEdit_loops.setValidator(QIntValidator(0, 99))
        self.lineEdit_cut_depth.setValidator(QDoubleValidator(0.0, 99.9, 3))
        self.lineEdit_safe_z.setValidator(QDoubleValidator(0.0, 999.9, 3))

        # setup event filter to catch focus_in events
        self.event_filter = EventFilter(self)
        parm_list = []
        for line in self.float_inputs:
            parm_list.append(line)
            self[f'lineEdit_{line}'].installEventFilter(self.event_filter)
        for line in self.int_inputs:
            parm_list.append(line)
            self[f'lineEdit_{line}'].installEventFilter(self.event_filter)
        self.lineEdit_comment.installEventFilter(self.event_filter)
        self.event_filter.set_line_list(parm_list)
        self.event_filter.set_kbd_list('comment')
        self.event_filter.set_tool_list('tool')
        self.event_filter.set_parms(('_enlarge_', True))

        # signal connections
        self.lineEdit_tool.editingFinished.connect(self.load_tool)
        self.chk_use_calc.stateChanged.connect(lambda state: self.event_filter.set_dialog_mode(state))
        self.chk_direction.stateChanged.connect(lambda state: self.direction_changed(state))
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
        code = bool(message.get('ID') == '_enlarge_')
        next = message.get('NEXT', False)
        back = message.get('BACK', False)
        if code and name == self.dialog_code:
            obj.setStyleSheet(self.default_style)
            if rtn is not None:
                if obj.objectName().replace('lineEdit_','') in ['spindle', 'loops', 'feed']:
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

    def load_tool(self, tool=None):
        #check for valid tool and populate dia
        if tool is None:
            tool = int(self.lineEdit_tool.text())
        info = TOOL.GET_TOOL_INFO(tool)
        self.lineEdit_tool_dia.setText(f"{info[11]:8.3f}")
        self.lineEdit_tool_info.setText(info[15])

    def save_program(self):
        if not self.validate(): return
        if not self.calculate_program():
            self.h.add_status('Unable to calculate program', ERROR)
            return
        caption = 'Save Hole Enlarge Program'
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
            self.h.add_status("Program save cancelled")

    def send_program(self):
        if not self.validate(): return
        if not self.calculate_program():
            self.h.add_status('Unable to calculate program', ERROR)
            return
        filename = self.make_temp('hole_enlarge')
        with open(filename, 'w') as f:
            f.write('\n'.join(self.gcode))
        self.preview_program(filename)
        ACTION.OPEN_PROGRAM(filename)
        self.h.add_status("Hole enlarge program sent to Linuxcnc")

    def preview_program(self, filename):
        result = self.preview.load_program(filename)
        if result:
            self.preview.set_path_points()
            self.preview.update()
        else:
            self.h.add_status('Program preview failed', WARNING)

    def validate(self):
        if not self.check_float_blanks(self.float_inputs): return False
        if not self.check_int_blanks(self.int_inputs): return False
        # additional checks
        for val in self.float_inputs:
            if self[val] <= 0.0:
                self[f'lineEdit_{val}'].setStyleSheet(self.red_border)
                self.h.add_status(f"{val} must be > 0.0", WARNING)
                return False
        if self.final_dia < self.start_dia:
            self.lineEdit_final_dia.setStyleSheet(self.red_border)
            self.h.add_status("Final diameter must be > start diameter", WARNING)
        if self.loops <= 0:
            self.lineEdit_loops.setStyleSheet(self.red_border)
            self.h.add_status("Number of loops must be > 0", WARNING)
            return False
        if self.feed <= 0:
            self.lineEdit_feed.setStyleSheet(self.red_border)
            self.h.add_status("Feed rate must be > 0", WARNING)
            return False
        if not (self.min_rpm <= self.spindle <= self.max_rpm):
            self.lineEdit_spindle.setStyleSheet(self.red_border)
            self.h.add_status(f'Spindle RPM must be between {self.min_rpm} and {self.max_rpm}', WARNING)
            return False
        return True

    def calculate_program(self):
        self.gcode = []
        unit_text = 'Metric' if INFO.MACHINE_IS_METRIC else 'Imperial'
        comment = self.lineEdit_comment.text()
        unit_code = 'G21' if INFO.MACHINE_IS_METRIC else 'G20'
        self.line_num = 5
        # opening preamble
        self.gcode.append("%")
        self.gcode.append(f"({comment})")
        self.gcode.append(f"(Start diameter is {self.start_dia})")
        self.gcode.append(f"(Final diameter is {self.final_dia})")
        self.gcode.append(f"(Depth of cut is {self.cut_depth})")
        self.gcode.append(f"(All units are {unit_text})\n")
        self.next_line(f"G40 G49 G64 P0.03 M6 T{self.tool}")
        self.next_line("G17")
        self.next_line(unit_code)
        if self.chk_mist.isChecked():
            self.next_line("M7")
        if self.chk_flood.isChecked():
            self.next_line("M8")
        self.next_line(f"G0 Z{self.safe_z}")
        offset = (self.start_dia - self.tool_dia) / 2
        self.next_line(f"G0 X{offset} Y0")
        self.next_line(f"M3 S{self.spindle}")
        self.next_line("G91")
        self.next_line(f"G1 Z-{self.safe_z + self.cut_depth} F{self.feed / 2}")
        self.next_line(f"F{self.feed}")
        steps = int((360 * self.loops) / self.angle_inc)
        inc = (self.final_dia - self.start_dia) / (2 * steps)
        angle = self.angle_inc if self.chk_direction.isChecked() else -self.angle_inc
        # create the spiral
        self.gcode.append(f"(Create spiral with {self.loops} loops)")
        self.next_line(f"o100 repeat [{steps}]")
        self.next_line(f"g91 g1 @{inc:8.4f} ^{angle}")
        self.next_line("o100 endrepeat")
        # final profile pass
        offset = (self.final_dia - self.tool_dia) / 2
        direction = "G3" if self.chk_direction.isChecked() else "G2"
        self.gcode.append("(Profile pass)")
        self.next_line(f"{direction} I-{offset:8.4f} F{self.feed}")
        self.post_amble()
        return True

    def set_unit_labels(self):
        unit = "MM" if INFO.MACHINE_IS_METRIC else "IN"
        self.lbl_feed_unit.setText(unit + "/MIN")
        for val in ['tool_dia', 'start_dia', 'final_dia', 'cut_depth', 'safe_z']:
            self[f'lbl_{val}_unit'].setText(unit)
        
    def direction_changed(self, state):
        text = "CCW" if state else "CW"
        self.chk_direction.setText(text)

    def next_line(self, text):
        self.gcode.append(f"N{self.line_num} {text}")
        self.line_num += 5

    def show_help(self):
        if self.parent is None: return
        fname = os.path.join(HELP, self.helpfile)
        self.parent.show_help_page(fname)

    # required code for subscriptable objects
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)
