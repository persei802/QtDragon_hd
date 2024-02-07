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

from PyQt5 import QtGui, QtWidgets, uic
from qtvcp.core import Info, Status, Action, Path
from qtvcp import logger

INFO = Info()
STATUS = Status()
ACTION = Action()
PATH = Path()
LOG = logger.getLogger(__name__)
HERE = os.path.dirname(os.path.abspath(__file__))
HELP = os.path.join(PATH.CONFIGPATH, "help_files")

class Auto_Measure(QtWidgets.QWidget):
    def __init__(self, widget, parent=None):
        super(Auto_Measure, self).__init__()
        self.w = widget
        self.parent = parent
        self.helpfile = 'height_measure_help.html'
        self.stat = linuxcnc.stat()
        if INFO.MACHINE_IS_METRIC:
            self.valid = QtGui.QDoubleValidator(-999.999, 999.999, 3)
        else:
            self.valid = QtGui.QDoubleValidator(-999.9999, 999.9999, 4)
        # Load the widgets UI file:
        self.filename = os.path.join(HERE, 'auto_height.ui')
        try:
            self.instance = uic.loadUi(self.filename, self)
        except AttributeError as e:
            print("Error: ", e)

        self.normal_color = ""
        self.error_color = "color: #ff0000;"
        self.send_dict = {}
        # define validators for all lineEdit widgets
        for i in ['x1', 'y1', 'z1', 'x2', 'y2', 'z2']:
            self['lineEdit_pos_' + i].setValidator(self.valid)

        # signal connections
        self.chk_enable_set.stateChanged.connect(self.chk_enable_changed)
        self.btn_set_wp.clicked.connect(self.set_position_clicked)
        self.btn_set_machine.clicked.connect(self.set_position_clicked)
        self.btn_start.clicked.connect(self.start)
        self.btn_help.pressed.connect(self.show_help)

    def _hal_init(self):
        self.actionbutton_abort.hal_init()
        def homed_on_status():
            return (STATUS.machine_is_on() and (STATUS.is_all_homed() or INFO.NO_HOME_REQUIRED))
        STATUS.connect('state_off', lambda w: self.setEnabled(False))
        STATUS.connect('state_estop', lambda w: self.setEnabled(False))
        STATUS.connect('interp-idle', lambda w: self.setEnabled(homed_on_status()))
        STATUS.connect('all-homed', lambda w: self.setEnabled(True))
        
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
            self.lineEdit_status.setText("Workpiece Probe position 1 set")
        elif btn == "mp":
            self.lineEdit_pos_x2.setText(f"{xyz[0]:.3f}")
            self.lineEdit_pos_y2.setText(f"{xyz[1]:.3f}")
            self.lineEdit_pos_z2.setText(f"{xyz[2]:.3f}")
            self.lineEdit_status.setText("Machine Probe position 2 set")

    def start(self):
        if not self.validate(): return
        self.lineEdit_status.setText("Auto height measurement started")
        self.send_dict['search_vel'] = self.w.lineEdit_search_vel.text()
        self.send_dict['probe_vel'] = self.w.lineEdit_probe_vel.text()
        self.send_dict['max_probe'] = self.w.lineEdit_max_probe.text()
        self.send_dict['retract_distance'] = self.w.lineEdit_retract.text()
        self.send_dict['z_safe_travel'] = self.w.lineEdit_zsafe.text()
        self.send_dict['pos_x1'] = self.lineEdit_pos_x1.text()
        self.send_dict['pos_y1'] = self.lineEdit_pos_y1.text()
        self.send_dict['pos_z1'] = self.lineEdit_pos_z1.text()
        self.send_dict['pos_x2'] = self.lineEdit_pos_x2.text()
        self.send_dict['pos_y2'] = self.lineEdit_pos_y2.text()
        self.send_dict['pos_z2'] = self.lineEdit_pos_z2.text()
        string_to_send = 'probe_z$' + json.dumps(self.send_dict) + '\n'
        print("String to send ", string_to_send)
        rtn = ACTION.AUTO_HEIGHT(string_to_send, self.autoheight_return, self.autoheight_error)
        if rtn == 0:
            self.lineEdit_status.setText("Autoheight routine is already running")

    def validate(self):
        valid = True
        # create lineEdit colors to indicate error state
        # placed here because changing stylesheets could change colors
        default_color = self.w.lineEdit_probe_tool.palette().color(self.w.lineEdit_probe_tool.foregroundRole())
        self.normal_color = f"color: {default_color.name()};"
        # restore normal text colors
        for item in ["search_vel", "probe_vel", "max_probe", "retract", "zsafe"]:
            widget = self.w['lineEdit_' + item]
            color = widget.palette().color(widget.foregroundRole())
            if color.name() == "#ff0000":
                widget.setStyleSheet(self.normal_color)
        # check search velocity
        try:
            if float(self.w.lineEdit_search_vel.text()) <= 0.0:
                self.w.lineEdit_search_vel.setStyleSheet(self.error_color)
                self.lineEdit_status.setText("Search velocity must be greater than 0.0")
                valid = False
        except:
            self.w.lineEdit_search_vel.setStyleSheet(self.error_color)
            valid = False
        # check probe velocity
        try:
            if float(self.w.lineEdit_probe_vel.text()) <= 0.0:
                self.w.lineEdit_probe_vel.setStyleSheet(self.error_color)
                self.lineEdit_status.setText("Probe velocity must be greater than 0.0")
                valid = False
        except:
            self.w.lineEdit_probe_vel.setStyleSheet(self.error_color)
            valid = False
        # check max probe distance
        try:
            if float(self.w.lineEdit_max_probe.text()) <= 0.0:
                self.w.lineEdit_max_probe.setStyleSheet(self.error_color)
                self.lineEdit_status.setText("Max probe must be greater than 0.0")
                valid = False
        except:
            self.w.lineEdit_max_probe.setStyleSheet(self.error_color)
            valid = False
        # check retract distance
        try:
            if float(self.w.lineEdit_retract.text()) <= 0.0:
                self.w.lineEdit_retract.setStyleSheet(self.error_color)
                self.lineEdit_status.setText("Retract distance must be greater than 0.0")
                valid = False
            elif float(self.w.lineEdit_retract.text()) > float(self.w.lineEdit_max_probe.text()):
                self.w.lineEdit_retract.setStyleSheet(self.error_color)
                self.lineEdit_status.setText("Retract distance must be less than max_probe")
                valid = False
        except:
            self.w.lineEdit_retract_distance.setStyleSheet(self.error_color)
            valid = False
        # check z safe height
        try:
            safe = float(self.w.lineEdit_zsafe.text())
            z1 = float(self.lineEdit_pos_z1.text())
            z2 = float(self.lineEdit_pos_z2.text())
            if safe <= z1 or z2 > z1:
                if safe <= z1:
                    error = "Z Safe height must be > than P1 Z height"
                else:
                    error = "P1 Z height must be >= P2 Z height"
                self.w.lineEdit_zsafe.setStyleSheet(self.error_color)
                self.lineEdit_status.setText(error)
                valid = False
        except:
            self.w.lineEdit_zsafe.setStyleSheet(self.error_color)
            valid = False
        return valid

    def show_help(self):
        fname = os.path.join(HELP, self.helpfile)
        self.parent.show_help_page(fname)

    def autoheight_return(self, data):
        rtn_dict = json.loads(data)
        diff = float(rtn_dict['z1']) - float(rtn_dict['z2'])
        self.lineEdit_height.setText(f"{diff:.3f}")
        if self.chk_autofill.isChecked():
            self.w.lineEdit_work_height.setText(f"{diff:.3f}")
        self.lineEdit_status.setText("Height measurement successfully completed")

    def autoheight_error(self, data):
        self.lineEdit_status.setText(data)

# required code for subscriptable iteration
    def __getitem__(self, item):
        return getattr(self, item)
    def __setitem__(self, item, value):
        return setattr(self, item, value)

# for standalone testing
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    w = Auto_Measure()
    w.show()
    sys.exit( app.exec_() )
