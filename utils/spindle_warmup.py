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

import sys
import os
import tempfile
import atexit
import pyqtgraph as pg

from lib.event_filter import EventFilter

from PyQt5 import QtGui, QtWidgets, uic
from pyqtgraph import PlotWidget, plot
from PyQt5.QtWidgets import QFileDialog
from qtvcp.core import Info, Action, Path, Status

INFO = Info()
ACTION = Action()
PATH = Path()
STATUS = Status()
HERE = os.path.dirname(os.path.abspath(__file__))
WARNING = 1


class Graph(pg.PlotWidget):
    def __init__(self):
        super(Graph, self).__init__()
        styles = {'color':'#FFFFFF', 'font-size':'12px'}
        self.setBackground(QtGui.QColor('#404040'))
        self.pen = pg.mkPen(color=(255, 0, 0), width=2)
        self.setTitle("Spindle Warmup Profile", color=QtGui.QColor('#FFFFFF'), size='14pt')
        self.setLabel('left', 'Speed (RPM)', **styles)
        self.setLabel('bottom', 'Time (MIN)', **styles)
        self.showGrid(x=True, y=True)

    def draw_graph(self, x, y):
        self.plot(x, y, pen=self.pen)


class Spindle_Warmup(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(Spindle_Warmup, self).__init__()
        self.parent = parent
        self.h = self.parent.parent
        self.dialog_code = 'CALCULATOR'
        self.kbd_code = 'KEYBOARD'
        self.default_style = ''
        self.red_border = "border: 2px solid red;"
        self.line_num = 0
        self.rpm = []
        self.steps = []
        self.start_rpm = 0
        self.final_rpm = 0
        self.interval = 0.0
        self.minimum_speed = INFO.MIN_SPINDLE_SPEED
        self.maximum_speed = INFO.MAX_SPINDLE_SPEED
        # Load the widgets UI file:
        self.filename = os.path.join(HERE, 'spindle_warmup.ui')
        try:
            self.instance = uic.loadUi(self.filename, self)
        except AttributeError as e:
            print("Error: ", e)
        self.preview = Graph()
        self.layout_graph.addWidget(self.preview)

        self.lineEdit_start.setValidator(QtGui.QIntValidator(0, 99999))
        self.lineEdit_final.setValidator(QtGui.QIntValidator(0, 99999))
        self.lineEdit_duration.setValidator(QtGui.QIntValidator(1, 999))
        self.lineEdit_steps.setValidator(QtGui.QIntValidator(1, 99))

        # setup event filter to catch focus_in events
        self.event_filter = EventFilter(self)
        line_list = ['start', 'final', 'duration', 'steps']
        for line in line_list:
            self[f'lineEdit_{line}'].installEventFilter(self.event_filter)
        self.lineEdit_comment.installEventFilter(self.event_filter)
        self.event_filter.set_line_list(line_list)
        self.event_filter.set_kbd_list('comment')
        self.event_filter.set_parms(('_warmup_', True))

        # signal connections
        self.chk_use_calc.stateChanged.connect(lambda state: self.event_filter.set_dialog_mode(state))
        self.btn_create.clicked.connect(self.create_program)
        self.btn_send.clicked.connect(self.send_program)

    def _hal_init(self):
        def homed_on_status():
            return (STATUS.machine_is_on() and (STATUS.is_all_homed() or INFO.NO_HOME_REQUIRED))
        STATUS.connect('general', self.dialog_return)
        STATUS.connect('state_off', lambda w: self.setEnabled(False))
        STATUS.connect('state_estop', lambda w: self.setEnabled(False))
        STATUS.connect('interp-idle', lambda w: self.setEnabled(homed_on_status()))
        STATUS.connect('all-homed', lambda w: self.setEnabled(True))

        self.default_style = self.lineEdit_start.styleSheet()

    def dialog_return(self, w, message):
        rtn = message['RETURN']
        name = message.get('NAME')
        obj = message.get('OBJECT')
        code = bool(message.get('ID') == '_warmup_')
        next = message.get('NEXT', False)
        back = message.get('BACK', False)
        if code and name == self.dialog_code:
            obj.setStyleSheet(self.default_style)
            if rtn is not None:
                obj.setText(f'{int(rtn)}')
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

    def create_program(self):
        if not self.validate(): return
        self.create_points()
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        sub_path = INFO.SUB_PATH_LIST
        _dir = os.path.expanduser(sub_path[0])
        fileName, _ = QFileDialog.getSaveFileName(self,"Save to file",_dir,"All Files (*);;ngc Files (*.ngc)", options=options)
        if fileName:
            self.calculate_program(fileName)
            self.h.add_status(f"{fileName} successfully created")
        else:
            self.h.add_status("Program creation aborted")

    def send_program(self):
        if not self.validate(): return
        self.create_points()
        filename = self.make_temp()[1]
        self.calculate_program(filename)
        ACTION.OPEN_PROGRAM(filename)
        self.h.add_status("Spindle warmup program sent to Linuxcnc")

    def validate(self):
        valid = True
        blank = "Input field cannot be blank"
        for item in ["steps", "duration", "start", "final"]:
            self['lineEdit_' + item].setStyleSheet(self.default_style)
        try:
            self.steps = int(self.lineEdit_steps.text())
            if self.steps < 2:
                self.lineEdit_steps.setStyleSheet(self.red_border)
                self.h.add_status("Error - Number of steps must be >= 2", WARNING)
                valid = False
        except:
            self.h.add_status(blank, WARNING)
            self.lineEdit_steps.setStyleSheet(self.red_border)
            valid = False

        try:
            self.duration = float(self.lineEdit_duration.text())
            if self.duration < 1:
                self.lineEdit_duration.setStyleSheet(self.red_border)
                self.h.add_status("Warmup duration must be >= 1", WARNING)
                valid = False
        except:
            self.h.add_status(blank, WARNING)
            self.lineEdit_duration.setStyleSheet(self.red_border)
            valid = False

        try:
            self.start_rpm = int(self.lineEdit_start.text())
            if self.start_rpm < self.minimum_speed:
                self.h.add_status("Start RPM adjusted to minimum spindle speed", WARNING)
                self.lineEdit_start.setText(str(self.minimum_speed))
                self.start_rpm = self.minimum_speed
        except:
            self.h.add_status(blank, WARNING)
            self.lineEdit_start.setStyleSheet(self.red_border)
            valid = False

        try:
            self.final_rpm = int(self.lineEdit_final.text())
            if self.final_rpm > self.maximum_speed:
                self.h.add_status("Final RPM adjusted to maximum spindle speed", WARNING)
                self.lineEdit_final.setText(str(self.maximum_speed))
                self.final_rpm = self.maximum_speed
        except:
            self.h.add_status(blank, WARNING)
            self.lineEdit_final.setStyleSheet(self.red_border)
            valid = False
        return valid

    def create_points(self):
        self.rpm = []
        speed = []
        time = []
        self.interval = float(self.duration/self.steps)
        speed_step = int((self.final_rpm - self.start_rpm)/(self.steps - 1))
        for i in range(self.steps):
            current_time = self.interval * i
            next_time = self.interval * (i + 1)
            current_speed =  (speed_step * i) + self.start_rpm
            time.append(current_time)
            time.append(next_time)
            speed.append(current_speed)
            speed.append(current_speed)
            self.rpm.append(current_speed)
        self.preview.clear()
        self.preview.draw_graph(time, speed)

    def create_gcode(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        fileName, _ = QFileDialog.getSaveFileName(self,"Save to file","","All Files (*);;ngc Files (*.ngc)", options=options)
        if fileName:
            self.calculate_program(fileName)
            self.h.add_status(f"{fileName} successfully created")
        else:
            print("Program creation aborted")

    def calculate_program(self, fname):
        comment = self.lineEdit_comment.text()
        self.line_num = 5
        self.file = open(fname, 'w')
        # opening preamble
        self.file.write("%\n")
        self.file.write(f"({comment})\n")
        self.file.write(f"(Warm up duration is {self.duration} minutes in {self.steps} steps)\n")
        self.file.write("\n")
        self.next_line("G40 G49 G64 P0.03")
        self.next_line("G17")
        if self.chk_mist.isChecked():
            self.next_line("M7")
        if self.chk_flood.isChecked():
            self.next_line("M8")
        for i in range(self.steps):
            self.next_line(f"S{self.rpm[i]} M3")
            self.next_line(f"G4 P{self.interval * 60:.2f}")
        self.next_line("M9")
        self.next_line("M5")
        self.next_line("M2")
        self.file.write("%\n")
        self.file.close()

    def next_line(self, text):
        self.file.write(f"N{self.line_num} " + text + "\n")
        self.line_num += 5

    def make_temp(self):
        _tmp = tempfile.mkstemp(prefix='spindle_warmup', suffix='.ngc')
        atexit.register(lambda: os.remove(_tmp[1]))
        return _tmp

    # required code for subscriptable objects
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    w = Spindle_Warmup()
    w.show()
    sys.exit( app.exec_() )

