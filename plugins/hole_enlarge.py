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
from qtpy import uic
from qtpy.QtCore import QSettings
from qtpy.QtGui import QIntValidator, QDoubleValidator
from qtpy.QtWidgets import QFileDialog, QLineEdit, QWidget
from qtvcp.core import Info, Status, Action, Tool, Path

from lib.event_filter import EventFilter
from plugins.utils_mixin import Common

INFO = Info()
PATH = Path()
TOOL = Tool()
STATUS = Status()
ACTION = Action()
HERE = os.path.dirname(os.path.abspath(__file__))
HELP = os.path.join(PATH.CONFIGPATH, "help_files")
WARNING = 1
ERROR = 2

PLUGIN_INFO = {
    'mod_name' : 'hole_enlarge',
    'class_name' : 'Hole_Enlarge',
    'item_text' : 'HOLE ENLARGE',
    'version' : '2.0',
    'description' : '''Hole Enlarge GCode generator
Create spiral toolpaths for enlarging a hole from a start diameter to end diameter
Programmable number of spiral loops to control stepover
Optional profile path for final cleanup
'''
}


class Hole_Enlarge(QWidget, Common):
    def __init__(self, parent=None):
        super(Hole_Enlarge, self).__init__()
        self.parent = parent
        self.settings = QSettings(os.path.join(HERE, 'settings.ini'), QSettings.IniFormat)
        self.helpfile = os.path.join(HELP, 'hole_enlarge_help.html')
        self.tmpl = '.3f' if INFO.MACHINE_IS_METRIC else '.4f'
        self.unit_text = ""
        self.angle_inc = 4

        # Load the widgets UI file:
        self.filename = os.path.join(HERE, 'hole_enlarge.ui')
        try:
            self.instance = uic.loadUi(self.filename, self)
        except AttributeError as e:
            print("Error: ", e)

        self.float_inputs = ['tool_dia', 'center_x', 'center_y', 'start_dia', 'final_dia', 'cut_depth', 'safe_z']
        self.int_inputs = ['tool', 'spindle', 'feed', 'loops']

        self.set_unit_labels()

        self.lineEdit_tool.setValidator(QIntValidator(1, 9999))
        self.lineEdit_center_x.setValidator(QDoubleValidator(-9999.9, 9999.9, 3))
        self.lineEdit_center_y.setValidator(QDoubleValidator(-9999.9, 9999.9, 3))
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
        self.btn_save.pressed.connect(lambda: self.create_program('save'))
        self.btn_send.pressed.connect(lambda: self.create_program('send'))
        self.btn_help.pressed.connect(lambda: self.parent.show_help(self.helpfile))

    def _hal_init(self):
        def homed_on_status():
            return (STATUS.machine_is_on() and (STATUS.is_all_homed() or INFO.NO_HOME_REQUIRED))
        STATUS.connect('general', self.dialog_return)
        STATUS.connect('state_off', lambda w: self.setEnabled(False))
        STATUS.connect('state_estop', lambda w: self.setEnabled(False))
        STATUS.connect('interp-idle', lambda w: self.setEnabled(homed_on_status()))
        STATUS.connect('all-homed', lambda w: self.setEnabled(True))
        self.default_style = self.lineEdit_tool.styleSheet()

        for line in self.int_inputs:
            self[f'lineEdit_{line}'].setText(self.settings.value(f'hole_enlarge/{line}', '0', str))
        for line in self.float_inputs:
            self[f'lineEdit_{line}'].setText(self.settings.value(f'hole_enlarge/{line}', '0', str))

    def closing_cleanup__(self):
        for line in self.int_inputs:
            self.settings.setValue(f'hole_enlarge/{line}', self[f'lineEdit_{line}'].text())
        for line in self.float_inputs:
            self.settings.setValue(f'hole_enlarge/{line}', self[f'lineEdit_{line}'].text())
        self.settings.sync()

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

    def create_program(self, mode):
        if not self.validate(): return
        if not self.calculate_gcode():
            self.parent.add_status('Unable to calculate gcode', ERROR)
            return
        if mode == 'send':
            filename = self.make_temp('hole_enlarge')
            with open(filename, 'w') as f:
                f.write('\n'.join(self.gcode))
            ACTION.OPEN_PROGRAM(filename)
            self.parent.add_status("Hole enlarge program sent to Linuxcnc")
        elif mode == 'save':
            caption = 'Save Hole Enlarge Program'
            _dir = os.path.expanduser('~/linuxcnc/nc_files')
            _filter = 'ngc Files (*.ngc)'
            fileName, _ = self.save_program_file(self, caption, _dir, _filter)
            if fileName:
                if self.gcode:
                    with open(fileName, 'w') as f:
                        f.write('\n'.join(self.gcode))
                    self.parent.add_status(f"Program saved to {fileName}")
            else:
                self.parent.add_status("Program save cancelled")

    def validate(self):
        if not self.check_float_blanks(self.float_inputs): return False
        if not self.check_int_blanks(self.int_inputs): return False
        # additional checks
        for val in self.float_inputs:
            if val in ["center_x", "center_y"]: pass
            elif self[val] <= 0.0:
                self[f'lineEdit_{val}'].setStyleSheet(self.red_border)
                self.parent.add_status(f"{val} must be > 0.0", WARNING)
                return False
        if self.final_dia < self.start_dia:
            self.lineEdit_final_dia.setStyleSheet(self.red_border)
            self.parent.add_status("Final diameter must be > start diameter", WARNING)
        if self.loops <= 0:
            self.lineEdit_loops.setStyleSheet(self.red_border)
            self.parent.add_status("Number of loops must be > 0", WARNING)
            return False
        if self.feed <= 0:
            self.lineEdit_feed.setStyleSheet(self.red_border)
            self.parent.add_status("Feed rate must be > 0", WARNING)
            return False
        if not (self.min_rpm <= self.spindle <= self.max_rpm):
            self.lineEdit_spindle.setStyleSheet(self.red_border)
            self.parent.add_status(f'Spindle RPM must be between {self.min_rpm} and {self.max_rpm}', WARNING)
            return False
        return True

    def calculate_gcode(self):
        self.gcode = []
        unit_text = 'Metric' if INFO.MACHINE_IS_METRIC else 'Imperial'
        comment = self.lineEdit_comment.text()
        unit_code = 'G21' if INFO.MACHINE_IS_METRIC else 'G20'
        # opening preamble
        self.gcode.append("%")
        self.gcode.append(f"({comment})")
        self.gcode.append(f"(Start diameter is {self.start_dia})")
        self.gcode.append(f"(Final diameter is {self.final_dia})")
        self.gcode.append(f"(Depth of cut is {self.cut_depth})")
        self.gcode.append(f"(Hole center at X{self.center_x} Y{self.center_y})")
        self.gcode.append(f"(All units are {unit_text})\n")
        self.gcode.append(f"G40 G49 G64 P0.03 M6 T{self.tool}")
        self.gcode.append("G17")
        self.gcode.append(unit_code)
        if self.chk_mist.isChecked():
            self.gcode.append("M7")
        if self.chk_flood.isChecked():
            self.gcode.append("M8")
        self.gcode.append(f"G0 Z{self.safe_z}")
        start = (self.start_dia - self.tool_dia) / 2
        # move to start point of spiral
        self.gcode.append(f"G0 X{self.center_x + start} Y{self.center_y}")
        self.gcode.append(f"M3 S{self.spindle}")
        self.gcode.append("G91")
        self.gcode.append(f"G1 Z-{self.safe_z + self.cut_depth} F{self.feed / 2}")
        self.gcode.append(f"F{self.feed}")
        # create the spiral
        steps = int((360 * self.loops) / self.angle_inc)
        dr = (self.final_dia - self.start_dia) / (2 * steps)
        angle = self.angle_inc if self.chk_direction.isChecked() else -self.angle_inc
        self.gcode.append("#1 = 1")
        self.gcode.append(f"#2 = {start}")
        self.gcode.append("#3 = 0")
        self.gcode.append("#8 = [#2 * COS[#3]]")
        self.gcode.append("#9 = [#2 * SIN[#3]]")
        self.gcode.append(f"(Create spiral with {self.loops} loops)")
        # WHILE LOOP
        self.gcode.append(f"O100 WHILE [#1 LT {steps}]")
        self.gcode.append(f"#2 = [{start} + [#1 * {dr}]]")
        self.gcode.append(f"#3 = [#1 * {angle}]")
        self.gcode.append("#4 = [#2 * COS[#3]]")
        self.gcode.append("#5 = [#2 * SIN[#3]]")
        self.gcode.append("#6 = [#4 - #8]")
        self.gcode.append("#7 = [#5 - #9]")
        self.gcode.append(f"G1 X#6 Y#7")
        self.gcode.append("#8 = #4")
        self.gcode.append("#9 = #5")
        self.gcode.append("#1 = [#1 + 1]")
        self.gcode.append("O100 ENDWHILE")
        # ENDWHILE
        # final profile pass
        self.gcode.append("G90")
        direction = "G3" if self.chk_direction.isChecked() else "G2"
        radius = (self.final_dia - self.tool_dia) / 2
        self.gcode.append("(Profile pass)")
        self.gcode.append(f"F{self.feed}")
        self.gcode.append(f"G0 X{self.center_x + radius} Y{self.center_y}")
        if direction == "G2":
            self.gcode.append(f"{direction} X{self.center_x} Y{self.center_y - radius} I{-radius} J0")
            self.gcode.append(f"{direction} X{self.center_x - radius} Y{self.center_y} I0 J{radius}")
            self.gcode.append(f"{direction} X{self.center_x} Y{self.center_y + radius} I{radius} J0")
            self.gcode.append(f"{direction} X{self.center_x + radius} Y{self.center_y} I0 J{-radius}")
        else:
            self.gcode.append(f"{direction} X{self.center_x} Y{self.center_y + radius} I{-radius} J0")
            self.gcode.append(f"{direction} X{self.center_x - radius} Y{self.center_y} I0 J{-radius}")
            self.gcode.append(f"{direction} X{self.center_x} Y{self.center_y - radius} I{radius} J0")
            self.gcode.append(f"{direction} X{self.center_x + radius} Y{self.center_y} I0 J{radius}")
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

    # required code for subscriptable objects
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)
