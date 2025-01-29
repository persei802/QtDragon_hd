#!/usr/bin/env python3
# Copyright (c) 2022 Jim Sloot (persei802@gmail.com)
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
import re
import math
import tempfile
import atexit
import shutil

from PyQt5 import QtGui, QtWidgets, uic
from PyQt5.QtWidgets import QWidget, QFileDialog
from qtvcp.core import Status, Action, Info, Path

INFO = Info()
STATUS = Status()
ACTION = Action()
PATH = Path()
HERE = os.path.dirname(os.path.abspath(__file__))
HELP = os.path.join(PATH.CONFIGPATH, "help_files")
WARNING = 1


class ZLevel(QWidget):
    def __init__(self, widget=None, handler=None, parent=None):
        super(ZLevel, self).__init__()
        self.w = widget
        self.h = handler
        self.parent = parent
        self.helpfile = 'zlevel_help.html'
        # Load the widgets UI file:
        self.filename = os.path.join(HERE, 'zlevel.ui')
        try:
            self.instance = uic.loadUi(self.filename, self)
        except AttributeError as e:
            print("Error: ", e)

        # Initial values
        self._tmp = None
        self.size_x = 0
        self.size_y = 0
        self.x_steps = 0
        self.y_steps = 0
        self.probe_tool = 0
        self.probe_vel = 0
        self.z_safe = 0
        self.max_probe = 0
        self.probe_filename = ""
        self.comp_file = ""
        self.red_border = "border: 2px solid red;"
        self.help_text = []
        # list of zero reference locations
        self.reference = ["top-left", "top-right", "center", "bottom-left", "bottom-right"]
        # set valid input formats for lineEdits
        self.lineEdit_size_x.setValidator(QtGui.QIntValidator(0, 9999))
        self.lineEdit_size_y.setValidator(QtGui.QIntValidator(0, 9999))
        self.lineEdit_steps_x.setValidator(QtGui.QIntValidator(0, 100))
        self.lineEdit_steps_y.setValidator(QtGui.QIntValidator(0, 100))
        self.lineEdit_probe_tool.setValidator(QtGui.QIntValidator(0, 100))
        units = "MM" if INFO.MACHINE_IS_METRIC else "IN"
        self.lbl_probe_area_unit.setText(units)

        # populate combobox
        self.cmb_zero_ref.addItems(self.reference)
        self.cmb_zero_ref.setCurrentIndex(2)

        # display default height map if available
        self.map_ready()

    def _hal_init(self):
        def homed_on_status():
            return (STATUS.machine_is_on() and (STATUS.is_all_homed() or INFO.NO_HOME_REQUIRED))
        STATUS.connect('state_off', lambda w: self.setEnabled(False))
        STATUS.connect('state_estop', lambda w: self.setEnabled(False))
        STATUS.connect('interp-idle', lambda w: self.setEnabled(homed_on_status()))
        STATUS.connect('all-homed', lambda w: self.setEnabled(True))
        STATUS.connect('file-loaded', lambda w, fname: self.lineEdit_gcode_program.setText(fname))

        # signal connections
        self.btn_save_gcode.pressed.connect(self.save_gcode)
        self.btn_send_gcode.pressed.connect(self.send_gcode)
        self.btn_load_comp.pressed.connect(self.load_comp_file)
        self.btn_get_maxz.pressed.connect(self.get_maxz)
        self.btn_help.pressed.connect(self.show_help)

        self.default_style = self.w.lineEdit_search_vel.styleSheet()

    def save_gcode(self):
        if not self.validate(): return
        fname = self.lineEdit_gcode_program.text()
        if os.path.exists(fname):
            dname = os.path.dirname(fname)
            pname = os.path.basename(fname)
            fname = os.path.join(dname, 'probe_' + pname)
        else:
            options = QFileDialog.Options()
            options |= QFileDialog.DontUseNativeDialog
            _filter = "Compensation Probe Files (*.ngc)"
            _dir = INFO.SUB_PATH_LIST[0]
            _caption = "Save Probe File"
            fname, _ =  QFileDialog.getSaveFileName(None, _caption, _dir, _filter, options=options)
        if fname.endswith('.ngc'):
            self.probe_filename = fname.replace(".ngc", ".txt")
            self.calculate_gcode(fname)
            self.h.add_status(f"Program successfully saved to {fname}")
        else:
            self.h.add_status("Invalid filename specified", WARNING)

    def send_gcode(self):
        if not self.validate(): return
        fname = self.make_temp()[1]
        self.probe_filename = os.path.join(PATH.CONFIGPATH, "probe_points.txt")
        self.calculate_gcode(fname)
        ACTION.OPEN_PROGRAM(fname)
        self.h.add_status("Program successfully sent to Linuxcnc")

    def calculate_gcode(self, fname):
        # get start point
        zref = self.cmb_zero_ref.currentIndex()
        if zref == 2:
            x_start = -self.size_x / 2
            y_start = -self.size_y / 2
        else:
            x_start = 0 if zref == 0 or zref == 3 else -self.size_x
            y_start = 0 if zref == 3 or zref == 4 else -self.size_y
        # calculate increments
        x_inc = self.size_x / (self.x_steps - 1)
        y_inc = self.size_y / (self.y_steps - 1)
        # opening preamble
        self.line_num = 5
        self.file = open(fname, 'w')
        self.file.write("%\n")
        self.file.write(f"({self.lineEdit_comment.text()})\n")
        self.file.write(f"(Area: X {self.size_x} by Y {self.size_y})\n")
        self.file.write(f"(Steps: X {self.x_steps} by Y {self.y_steps})\n")
        self.file.write(f"(Safe Z travel height {self.z_safe})\n")
        self.file.write(f"(XY Zero point is {self.reference[zref]})\n")
        self.next_line("G17 G40 G49 G64 G90 P0.03")
        self.next_line("G92.1")
        self.next_line(f"M6 T{self.probe_tool}")
        self.next_line(f"G0 Z{self.z_safe}")
        # main section
        self.next_line(f"(PROBEOPEN {self.probe_filename})")
        self.next_line("#100 = 0")
        self.next_line(f"O100 while [#100 LT {self.y_steps}]")
        self.next_line(f"  G0 Y[{y_start} + {y_inc:.3f} * #100]")
        self.next_line("  #200 = 0")
        self.next_line(f"  O200 while [#200 LT {self.x_steps}]")
        self.next_line(f"    G0 X[{x_start} + {x_inc:.3f} * #200]")
        self.next_line(f"    G38.2 Z-{self.max_probe} F{self.probe_vel}")
        self.next_line(f"    G0 Z{self.z_safe}")
        self.next_line("    #200 = [#200 + 1]")
        self.next_line("  O200 endwhile")
        self.next_line("  #100 = [#100 + 1]")
        self.next_line("O100 endwhile")
        self.next_line("(PROBECLOSE)")
        # closing section
        self.next_line("M2")
        self.file.write("%\n")
        self.file.close()

    def validate(self):
        valid = True
        # restore normal border colors
        for item in ["size_x", "size_y", "steps_x", "steps_y"]:
            if self['lineEdit_' + item].styleSheet() == self.red_border:
                self['lineEdit_' + item].setStyleSheet(self.default_style)
        for item in ["zsafe", "probe_vel", "max_probe"]:
            if self.w['lineEdit_' + item].styleSheet() == self.red_border:
                self.w['lineEdit_' + item].setStyleSheet(self.default_style)
        if self.lineEdit_probe_tool.styleSheet == self.red_border:
            self.lineEdit_probe_tool.setStyleSheet(self.default_style)
        # check array size parameter
        try:
            self.size_x = float(self.lineEdit_size_x.text())
            if self.size_x <= 0:
                self.lineEdit_size_x.setStyleSheet(self.red_border)
                self.h.add_status("Size X must be > 0", WARNING)
                valid = False
        except:
            self.lineEdit_size_x.setStyleSheet(self.red_border)
            valid = False
        try:
            self.size_y = float(self.lineEdit_size_y.text())
            if self.size_y <= 0:
                self.lineEdit_size_y.setStyleSheet(self.red_border)
                self.h.add_status("Size Y must be > 0", WARNING)
                valid = False
        except:
            self.lineEdit_size_y.setStyleSheet(self.red_border)
            valid = False
        # check array steps parameter
        try:
            self.x_steps = int(self.lineEdit_steps_x.text())
            if self.x_steps < 2:
                self.lineEdit_steps_x.setStyleSheet(self.red_border)
                self.h.add_status("Steps X must be >= 2", WARNING)
                valid = False
        except:
            self.lineEdit_steps_x.setStyleSheet(self.red_border)
            valid = False
        try:
            self.y_steps = int(self.lineEdit_steps_y.text())
            if self.y_steps < 2:
                self.lineEdit_steps_y.setStyleSheet(self.red_border)
                self.h.add_status("Steps Y must be >= 2", WARNING)
                valid = False
        except:
            self.lineEdit_steps_y.setStyleSheet(self.red_border)
            valid = False
        # check probe tool number
        try:
            self.probe_tool = int(self.lineEdit_probe_tool.text())
            if self.probe_tool <= 0:
                self.w.lineEdit_probe_tool.setStyleSheet(self.red_border)
                self.h.add_status("Probe tool number must be > 0", WARNING)
                valid = False
        except:
            self.w.lineEdit_probe_tool.setStyleSheet(self.red_border)
            valid = False
        # check z safe parameter
        try:
            self.z_safe = float(self.w.lineEdit_zsafe.text())
            if self.z_safe <= 0.0:
                self.w.lineEdit_zsafe.setStyleSheet(self.red_border)
                self.h.add_status("Z safe height must be > 0", WARNING)
                valid = False
        except:
            self.w.lineEdit_zsafe.setStyleSheet(self.red_border)
            valid = False
        # check probe velocity
        try:
            self.probe_vel = float(self.w.lineEdit_probe_vel.text())
            if self.probe_vel <= 0.0:
                self.h.add_status("Slow probing sequence will be skipped", WARNING)
        except:
            self.w.lineEdit_probe_vel.setStyleSheet(self.red_border)
            valid = False
        # check max probe distance
        try:
            self.max_probe = float(self.w.lineEdit_max_probe.text())
            if self.max_probe <= 0.0:
                self.w.lineEdit_max_probe.setStyleSheet(self.red_border)
                self.h.add_status("Max probe distance must be > 0", WARNING)
                valid = False
        except:
            self.w.lineEdit_max_probe.setStyleSheet(self.red_border)
            valid = False
        return valid

    def next_line(self, text):
        self.file.write(f"N{self.line_num} " + text + "\n")
        self.line_num += 5

    def map_ready(self):
        fname = os.path.join(PATH.CONFIGPATH, "height_map.png")
        if os.path.isfile(fname):
            self.lbl_height_map.setPixmap(QtGui.QPixmap(fname))
        else:
            self.lbl_height_map.setText("Height Map not available")
        
    def load_comp_file(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        _filter = "Compensation Files (*.txt)"
        _dir = INFO.SUB_PATH_LIST[0]
        _caption = "Load Compensation File"
        fname, _ =  QFileDialog.getOpenFileName(None, _caption, _dir, _filter, options=options)
        if fname:
            self.comp_file = fname
            self.lbl_height_map.setText("Toggle ZCOMP ENABLE to ON to generate new height map")
            self.lbl_comp_file.setText(os.path.basename(fname))
            dst = os.path.join(PATH.CONFIGPATH, "probe_points.txt")
            try:
                shutil.copy(fname, dst)
                self.h.add_status(f"Loaded compensation file {fname}")
            except Exception as e:
                self.h.add_status(e, WARNING)

    def get_maxz(self):
        fname = os.path.join(PATH.CONFIGPATH, "probe_points.txt")
        if os.path.isfile(fname):
            zmax = -999.0
            high = (0, 0, zmax)
            with open(fname, 'r') as file:
                lines = file.readlines()
            for line in lines:
                axis = line.split(" ")
                if float(axis[2]) > zmax:
                    zmax = float(axis[2])
                    high = (float(axis[0]), float(axis[1]), float(axis[2]))
            self.lbl_highest.setText(f"Highest point is at X: {high[0]:.1f}  Y: {high[1]:.1f} Z: {high[2]:.1f}")
        else:
            self.lbl_highest.setText("Highest point undefined")
            self.h.add_status("No probe_points.txt file in CONFIG directory", WARNING)

    def get_map(self):
        return self.comp_file

    def set_comp_area(self, data):
        units = data[2]
        line_x = data[0]
        numbers = re.findall(r'-?\d+\.?\d*', line_x)
        span_x = float(numbers[2])
        line_y = data[1]
        numbers = re.findall(r'-?\d+\.?\d*', line_y)
        span_y = float(numbers[2])
        if units == 'in':
            span_x = span_x * 25.4
            span_y = span_y * 25.4
        span_x = math.ceil(span_x)
        span_y = math.ceil(span_y)
        self.lineEdit_size_x.setText(str(span_x))
        self.lineEdit_size_y.setText(str(span_y))

    def show_help(self):
        fname = os.path.join(HELP, self.helpfile)
        self.parent.show_help_page(fname)

    def make_temp(self):
        _tmp = tempfile.mkstemp(prefix='zlevel', suffix='.ngc')
        atexit.register(lambda: os.remove(_tmp[1]))
        return _tmp

    # required code for subscriptable objects
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)

# for standalone testing
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    w = ZLevel()
    w.show()
    sys.exit( app.exec_() )

