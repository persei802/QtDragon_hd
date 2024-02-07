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

class ZLevel(QWidget):
    def __init__(self, widget=None, parent=None):
        super(ZLevel, self).__init__()
        self.w = widget
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
        self.probe_start = 0
        self.probe_filename = None
        self.comp_file = None
        self.normal_color = ""
        self.error_color = "color: #ff0000;"
        self.help_text = []
        # list of zero reference locations
        self.reference = ["top-left", "top-right", "center", "bottom-left", "bottom-right"]
        # set valid input formats for lineEdits
        self.lineEdit_size_x.setValidator(QtGui.QDoubleValidator(0, 999, 3))
        self.lineEdit_size_y.setValidator(QtGui.QDoubleValidator(0, 999, 3))
        self.lineEdit_steps_x.setValidator(QtGui.QIntValidator(0, 100))
        self.lineEdit_steps_y.setValidator(QtGui.QIntValidator(0, 100))
        units = "MM" if INFO.MACHINE_IS_METRIC else "IN"
        self.lbl_probe_area_unit.setText(units)

        # populate combobox
        self.cmb_zero_ref.addItems(self.reference)
        self.cmb_zero_ref.setCurrentIndex(2)

        # signal connections
        self.btn_save_gcode.pressed.connect(self.save_gcode)
        self.btn_send_gcode.pressed.connect(self.send_gcode)
        self.btn_load_comp.pressed.connect(self.load_comp_file)
        self.btn_help.pressed.connect(self.show_help)

        # display default height map if available
        self.map_ready()

    def _hal_init(self):
        def homed_on_status():
            return (STATUS.machine_is_on() and (STATUS.is_all_homed() or INFO.NO_HOME_REQUIRED))
        STATUS.connect('state_off', lambda w: self.setEnabled(False))
        STATUS.connect('state_estop', lambda w: self.setEnabled(False))
        STATUS.connect('interp-idle', lambda w: self.setEnabled(homed_on_status()))
        STATUS.connect('all-homed', lambda w: self.setEnabled(True))

    def save_gcode(self):
        if not self.validate(): return
        fname = self.lineEdit_probe_points.text()
        fname = fname.replace(".txt", ".ngc")
        fileName = os.path.join(INFO.SUB_PATH_LIST[0], fname)
        fileName = os.path.expanduser(fileName)
        self.calculate_gcode(fileName)
        self.lineEdit_status.setText(f"Program successfully saved to {fileName}")

    def send_gcode(self):
        if not self.validate(): return
        filename = self.make_temp()[1]
        self.calculate_gcode(filename)
        ACTION.OPEN_PROGRAM(filename)
        self.lineEdit_status.setText("Program successfully sent to Linuxcnc")

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
        self.next_line(f"  G0 Y[{y_start} + {y_inc} * #100]")
        self.next_line("  #200 = 0")
        self.next_line(f"  O200 while [#200 LT {self.x_steps}]")
        self.next_line(f"    G0 X[{x_start} + {x_inc} * #200]")
        self.next_line(f"    G0 Z{self.probe_start}")
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
        # create lineEdit colors to indicate error state
        # placed here because changing stylesheets could change colors
        default_color = self.w.lineEdit_probe_tool.palette().color(self.w.lineEdit_probe_tool.foregroundRole())
        self.normal_color = f"color: {default_color.name()};"
        # restore normal text colors
        for item in ["size_x", "size_y", "steps_x", "steps_y", "probe_points"]:
            widget = self['lineEdit_' + item]
            color = widget.palette().color(widget.foregroundRole())
            if color.name() == "#ff0000":
                widget.setStyleSheet(self.normal_color)
        for item in ["probe_tool", "zsafe", "probe_vel", "max_probe", "probe_start"]:
            widget = self.w['lineEdit_' + item]
            color = widget.palette().color(widget.foregroundRole())
            if color.name() == "#ff0000":
                widget.setStyleSheet(self.normal_color)
        # check array size parameter
        try:
            self.size_x = float(self.lineEdit_size_x.text())
            if self.size_x <= 0:
                self.lineEdit_size_x.setStyleSheet(self.error_color)
                self.lineEdit_status.setText("Size X must be > 0")
                valid = False
        except:
            self.lineEdit_size_x.setStyleSheet(self.error_color)
            valid = False
        try:
            self.size_y = float(self.lineEdit_size_y.text())
            if self.size_y <= 0:
                self.lineEdit_size_y.setStyleSheet(self.error_color)
                self.lineEdit_status.setText("Size Y must be > 0")
                valid = False
        except:
            self.lineEdit_size_y.setStyleSheet(self.error_color)
            valid = False
        # check array steps parameter
        try:
            self.x_steps = int(self.lineEdit_steps_x.text())
            if self.x_steps < 2:
                self.lineEdit_steps_x.setStyleSheet(self.error_color)
                self.lineEdit_status.setText("Steps X must be >= 2")
                valid = False
        except:
            self.lineEdit_steps_x.setStyleSheet(self.error_color)
            valid = False
        try:
            self.y_steps = int(self.lineEdit_steps_y.text())
            if self.y_steps < 2:
                self.lineEdit_steps_y.setStyleSheet(self.error_color)
                self.lineEdit_status.setText("Steps Y must be >= 2")
                valid = False
        except:
            self.lineEdit_steps_y.setStyleSheet(self.error_color)
            valid = False
        # check probe tool number
        try:
            self.probe_tool = int(self.w.lineEdit_probe_tool.text())
            if self.probe_tool <= 0:
                self.w.lineEdit_probe_tool.setStyleSheet(self.error_color)
                self.lineEdit_status.setText("Probe tool number must be > 0")
                valid = False
        except:
            self.w.lineEdit_probe_tool.setStyleSheet(self.error_color)
            valid = False
        # check z safe parameter
        try:
            self.z_safe = float(self.w.lineEdit_zsafe.text())
            if self.z_safe <= 0.0:
                self.w.lineEdit_zsafe.setStyleSheet(self.error_color)
                self.lineEdit_status.setText("Z safe height must be > 0")
                valid = False
        except:
            self.w.lineEdit_zsafe.setStyleSheet(self.error_color)
            valid = False
        # check probe velocity
        try:
            self.probe_vel = float(self.w.lineEdit_probe_vel.text())
            if self.probe_vel <= 0.0:
                self.lineEdit_status.setText("Slow probing sequence will be skipped")
        except:
            self.w.lineEdit_probe_vel.setStyleSheet(self.error_color)
            valid = False
        # check max probe distance
        try:
            self.max_probe = float(self.w.lineEdit_max_probe.text())
            if self.max_probe <= 0.0:
                self.w.lineEdit_max_probe.setStyleSheet(self.error_color)
                self.lineEdit_status.setText("Max probe distance must be > 0")
                valid = False
        except:
            self.w.lineEdit_max_probe.setStyleSheet(self.error_color)
            valid = False
        # check probe start height
        try:
            self.probe_start = float(self.w.lineEdit_probe_start.text())
            if self.probe_start <= 0.0:
                self.w.lineEdit_probe_start.setStyleSheet(self.error_color)
                self.lineEdit_status.setText("Start probe height must be > 0")
                valid = False
            elif self.probe_start > self.z_safe:
                self.w.lineEdit_probe_start.setStyleSheet(self.error_color)
                self.lineEdit_status.setText("Start probe height must be < Z Safe height")
                valid = False
            elif self.probe_start > self.max_probe:
                self.w.lineEdit_probe_start.setStyleSheet(self.error_color)
                self.lineEdit_status.setText("Start probe height must be < Max Probe distance")
                valid = False
        except:
            self.w.lineEdit_probe_start.setStyleSheet(self.error_color)
            valid = False
        # check probe points filename
        try:
            self.probe_filename = self.lineEdit_probe_points.text()
            if not self.probe_filename.endswith(".txt"):
                self.lineEdit_probe_points.setStyleSheet(self.error_color)
                self.lineEdit_status.setText("Probe points filename must end with .txt")
                valid = False
        except:
            self.lineEdit_probe_points.setStyleSheet(self.error_color)
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
            self.lbl_height_map.setText("Waiting for height map generation")
            self.lbl_comp_file.setText(os.path.basename(fname))
            self.lineEdit_status.setText(f"Loaded compensation file {fname}")
            dst = os.path.join(PATH.CONFIGPATH, "probe_points.txt")
            shutil.copy(fname, dst)

    def get_map(self):
        return self.comp_file

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

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    w = ZLevel()
    w.show()
    sys.exit( app.exec_() )

