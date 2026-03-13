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
import pyqtgraph as pg

from lib.event_filter import EventFilter
from utils.utils_mixin import Common

from pyqtgraph import PlotWidget, plot
from PyQt5 import uic
from PyQt5.QtGui import QColor, QIntValidator
from PyQt5.QtWidgets import QWidget, QFileDialog, QLineEdit
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
        self.setBackground(QColor('#404040'))
        self.pen = pg.mkPen(color=(255, 0, 0), width=2)
        self.setTitle("Spindle Warmup Profile", color=QColor('#FFFFFF'), size='14pt')
        self.setLabel('left', 'Speed (RPM)', **styles)
        self.setLabel('bottom', 'Time (MIN)', **styles)
        self.showGrid(x=True, y=True)

    def draw_graph(self, x, y):
        self.plot(x, y, pen=self.pen)


class Spindle_Warmup(QWidget, Common):
    def __init__(self, parent=None):
        super(Spindle_Warmup, self).__init__()
        self.parent = parent
        self.h = self.parent.parent
        self.line_num = 0
        self.rpm = []
        self.geometry = None
        # Load the widgets UI file:
        self.filename = os.path.join(HERE, 'spindle_warmup.ui')
        try:
            self.instance = uic.loadUi(self.filename, self)
        except AttributeError as e:
            print("Error: ", e)
        self.preview = Graph()
        self.layout_graph.addWidget(self.preview)

        self.inputs = ['start', 'final', 'duration', 'steps']

        self.lineEdit_start.setValidator(QIntValidator(0, 99999))
        self.lineEdit_final.setValidator(QIntValidator(0, 99999))
        self.lineEdit_duration.setValidator(QIntValidator(1, 999))
        self.lineEdit_steps.setValidator(QIntValidator(1, 99))

        # setup event filter to catch focus_in events
        self.event_filter = EventFilter(self)
        for line in self.inputs:
            self[f'lineEdit_{line}'].installEventFilter(self.event_filter)
        self.lineEdit_comment.installEventFilter(self.event_filter)
        self.event_filter.set_line_list(self.inputs)
        self.event_filter.set_kbd_list('comment')
        self.event_filter.set_parms(('_warmup_', True))

        # signal connections
        self.chk_use_calc.stateChanged.connect(lambda state: self.event_filter.set_dialog_mode(state))
        self.btn_send.pressed.connect(self.send_program)
        self.btn_save.pressed.connect(self.save_program)

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

    def validate(self):
        if not self.check_int_blanks(self.inputs): return False
        # additional checks
        if self.steps < 2:
            self.lineEdit_steps.setStyleSheet(self.red_border)
            self.h.add_status("Number of steps must be >= 2", WARNING)
            return False
        if self.duration < 1:
            self.lineEdit_duration.setStyleSheet(self.red_border)
            self.h.add_status("Warmup duration must be >= 1", WARNING)
            return False
        if not (self.min_rpm <= self.start <= self.max_rpm):
            self.lineEdit_start.setStyleSheet(self.red_border)
            self.h.add_status(f'Start RPM must be between {self.min_rpm} and {self.max_rpm}', WARNING)
            return False
        if not (self.min_rpm <= self.final <= self.max_rpm):
            self.lineEdit_final.setStyleSheet(self.red_border)
            self.h.add_status(f'Final RPM must be between {self.min_rpm} and {self.max_rpm}', WARNING)
            return False
        return True

    def create_points(self):
        self.rpm = []
        speed = []
        time = []
        self.interval = float(self.duration/self.steps)
        speed_step = int((self.final - self.start)/(self.steps - 1))
        for i in range(self.steps):
            current_time = self.interval * i
            next_time = self.interval * (i + 1)
            current_speed =  (speed_step * i) + self.start
            time.append(current_time)
            time.append(next_time)
            speed.append(current_speed)
            speed.append(current_speed)
            self.rpm.append(current_speed)
        self.preview.clear()
        self.preview.draw_graph(time, speed)

    def send_program(self):
        if not self.validate(): return
        self.create_points()
        self.calculate_program()
        filename = self.make_temp('spindle_warmup')
        with open(filename, 'w') as f:
            f.write('\n'.join(self.gcode))
        ACTION.OPEN_PROGRAM(filename)
        self.h.add_status("Spindle warmup program sent to Linuxcnc")

    def save_program(self):
        if not self.validate(): return
        self.create_points()
        self.calculate_program()
        caption = 'Save Spindle Warmup Program'
        _dir = os.path.expanduser('~/linuxcnc/nc_files')
        _filter = 'ngc Files (*.ngc)'
        fileName, _ = self.save_program_file(self, caption, _dir, _filter)
        if fileName:
            if self.gcode:
                with open(fileName, 'w') as f:
                    f.write('\n'.join(self.gcode))
                self.h.add_status(f"Program saved to {fileName}")
        else:
            self.h.add_status("Program save cancelled")

    def calculate_program(self):
        self.gcode = []
        comment = self.lineEdit_comment.text()
        self.line_num = 5
        # opening preamble
        self.gcode.append("%")
        self.gcode.append(f"({comment})")
        self.gcode.append(f"(Warm up duration is {self.duration} minutes in {self.steps} steps)")
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
        self.gcode.append("%")

    def next_line(self, text):
        self.gcode.append(f"N{self.line_num} {text}")
        self.line_num += 5

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

