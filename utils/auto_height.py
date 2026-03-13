#!/usr/bin/env python3
# Copyright (c) 2022  Jim Sloot <persei802@gmail.com>
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

import sys
import os
import linuxcnc
import json

from PyQt5 import uic
from PyQt5.QtGui import QDoubleValidator
from PyQt5.QtWidgets import QWidget, QApplication
from qtvcp.core import Info, Status, Action, Path
from lib.event_filter import EventFilter
from utils.utils_mixin import Common

INFO = Info()
STATUS = Status()
ACTION = Action()
PATH = Path()
HERE = os.path.dirname(os.path.abspath(__file__))
HELP = os.path.join(PATH.CONFIGPATH, "help_files")

WARNING = 1


class Auto_Measure(QWidget, Common):
    def __init__(self, parent=None):
        super(Auto_Measure, self).__init__()
        self.parent = parent
        self.w = self.parent.w
        self.h = self.parent.parent
        self.dialog_code = 'CALCULATOR'
        self.helpfile = 'height_measure_help.html'
        self.stat = linuxcnc.stat()
        self.send_dict = {}
        self.line_list = ['pos_x1', 'pos_y1', 'pos_z1', 'pos_x2', 'pos_y2', 'pos_z2',
                          'search_vel', 'probe_vel', 'max_probe', 'retract', 'zsafe']
        if INFO.MACHINE_IS_METRIC:
            self.tmpl = '.3f'
            self.valid = QDoubleValidator(-999.999, 999.999, 3)
        else:
            self.tmpl = '.4f'
            self.valid = QDoubleValidator(-999.9999, 999.9999, 4)
        # Load the widgets UI file:
        self.filename = os.path.join(HERE, 'auto_height.ui')
        try:
            self.instance = uic.loadUi(self.filename, self)
        except AttributeError as e:
            print("Error: ", e)

        # define validators for all lineEdit widgets
        for i in self.line_list:
            self['lineEdit_' + i].setValidator(self.valid)
        # set units according to machine type
        self.set_unit_labels()
        # setup event filter to catch focus_in events
        self.event_filter = EventFilter(self)
        for line in self.line_list:
            self[f'lineEdit_{line}'].installEventFilter(self.event_filter)
        self.event_filter.set_line_list(self.line_list)
        self.event_filter.set_parms(('_auto_height_', True))

    def _hal_init(self):
        self.actionbutton_abort.hal_init()
        def homed_on_status():
            return (STATUS.machine_is_on() and (STATUS.is_all_homed() or INFO.NO_HOME_REQUIRED))
        STATUS.connect('general', self.dialog_return)
        STATUS.connect('state_off', lambda w: self.setEnabled(False))
        STATUS.connect('state_estop', lambda w: self.setEnabled(False))
        STATUS.connect('interp-idle', lambda w: self.setEnabled(homed_on_status()))
        STATUS.connect('all-homed', lambda w: self.setEnabled(True))

        # signal connections
        self.chk_enable_set.stateChanged.connect(self.chk_enable_changed)
        self.chk_use_calc.stateChanged.connect(lambda state: self.event_filter.set_dialog_mode(state))
        self.btn_set_wp.clicked.connect(self.set_position_clicked)
        self.btn_set_machine.clicked.connect(self.set_position_clicked)
        self.btn_start.clicked.connect(self.start)
        self.btn_help.pressed.connect(self.show_help)

        self.default_style = self.lineEdit_search_vel.styleSheet()
        
    def dialog_return(self, w, message):
        rtn = message['RETURN']
        name = message.get('NAME')
        obj = message.get('OBJECT')
        code = bool(message.get('ID') == '_auto_height_')
        next = message.get('NEXT', False)
        back = message.get('BACK', False)
        if code and name == self.dialog_code:
            obj.setStyleSheet(self.default_style)
            if rtn is not None:
                obj.setText(f'{rtn:{self.tmpl}}')
            # request for next input widget from linelist
            if next:
                newobj = self.event_filter.findNext()
                self.event_filter.show_calc(newobj, True)
            elif back:
                newobj = self.event_filter.findBack()
                self.event_filter.show_calc(newobj, True)

    def chk_enable_changed(self, state):
        self.btn_set_wp.setEnabled(state)
        self.btn_set_machine.setEnabled(state)

    def set_position_clicked(self):
        btn = self.sender().property('btn')
        xyz = []
        self.stat.poll()
        pos = self.stat.actual_position
        off = self.stat.g5x_offset
        tlo = self.stat.tool_offset
        for i in range(3):
            xyz.append(pos[i] - off[i] - tlo[i])
        if btn == "wp":
            self.lineEdit_pos_x1.setText(f"{xyz[0]:.3f}")
            self.lineEdit_pos_y1.setText(f"{xyz[1]:.3f}")
            self.lineEdit_pos_z1.setText(f"{xyz[2]:.3f}")
            self.h.add_status("Workpiece Probe position 1 set")
        elif btn == "mp":
            self.lineEdit_pos_x2.setText(f"{xyz[0]:.3f}")
            self.lineEdit_pos_y2.setText(f"{xyz[1]:.3f}")
            self.lineEdit_pos_z2.setText(f"{xyz[2]:.3f}")
            self.h.add_status("Machine Probe position 2 set")

    def start(self):
        if not self.validate(): return
        self.h.add_status("Auto height measurement started")
        self.send_dict['search_vel'] = self.lineEdit_search_vel.text()
        self.send_dict['probe_vel'] = self.lineEdit_probe_vel.text()
        self.send_dict['max_probe'] = self.lineEdit_max_probe.text()
        self.send_dict['retract_distance'] = self.lineEdit_retract.text()
        self.send_dict['z_safe_travel'] = self.lineEdit_zsafe.text()

        self.send_dict['pos_x1'] = self.lineEdit_pos_x1.text()
        self.send_dict['pos_y1'] = self.lineEdit_pos_y1.text()
        self.send_dict['pos_z1'] = self.lineEdit_pos_z1.text()
        self.send_dict['pos_x2'] = self.lineEdit_pos_x2.text()
        self.send_dict['pos_y2'] = self.lineEdit_pos_y2.text()
        self.send_dict['pos_z2'] = self.lineEdit_pos_z2.text()
        string_to_send = 'probe_z$' + json.dumps(self.send_dict) + '\n'
#        print("String to send ", string_to_send)
        rtn = ACTION.AUTO_HEIGHT(string_to_send, self.autoheight_return, self.autoheight_error)
        if rtn == 0:
            self.h.add_status("Autoheight routine is already running", WARNING)

    def validate(self):
        # check for blanks
        if not self.check_float_blanks(self.line_list): return False
        # check for zeroes
        for val in ['search_vel', 'probe_vel', 'max_probe', 'retract', 'zsafe']:
            if self[val] <= 0.0:
                self[f'lineEdit_{val}'].setStyleSheet(self.red_border)
                self.h.add_status(f'{val} must be > 0', WARNING)
                return False
        # additional checks
        if self.retract > self.max_probe:
            self.lineEdit_retract.setStyleSheet(self.red_border)
            self.h.add_status(f'Retract distance must be < {self.max_probe}', WARNING)
            return False
        _max = max(self.pos_z1, self.pos_z2)
        if self.zsafe <= _max:
            self.lineEdit_zsafe.setStyleSheet(self.red_border)
            self.h.add_status(f'Z Safe height must be > {_max}', WARNING)
            return False
        return True

    def show_help(self):
        fname = os.path.join(HELP, self.helpfile)
        self.parent.show_help_page(fname)

    def autoheight_return(self, data):
        rtn_dict = json.loads(data)
        diff = float(rtn_dict['z1']) - float(rtn_dict['z2'])
        self.lineEdit_height.setText(f"{diff:.3f}")
        if self.chk_autofill.isChecked():
            self.w.lineEdit_work_height.setText(f"{diff:.3f}")
        self.h.add_status("Height measurement successfully completed")

    def autoheight_error(self, data):
        self.h.add_status(data, WARNING)

    def set_unit_labels(self):
        unit = 'MM' if INFO.MACHINE_IS_METRIC else 'IN'
        for val in ['search', 'probe']:
            self[f'lbl_{val}_unit'].setText(f'{unit}/MIN')
        for val in ['max_probe', 'retract', 'zsafe', 'height']:
            self[f'lbl_{val}_unit'].setText(unit)

# required code for subscriptable iteration
    def __getitem__(self, item):
        return getattr(self, item)
    def __setitem__(self, item, value):
        return setattr(self, item, value)

# for standalone testing
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Auto_Measure()
    w.show()
    sys.exit( app.exec_() )
