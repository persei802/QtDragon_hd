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
import sys
import os
import math
import tempfile
import atexit

from lib.event_filter import EventFilter

from PyQt5 import QtCore, QtGui, QtWidgets, uic
from PyQt5.QtCore import QPoint, QPointF, QLine, QRect, QFile, Qt, QEvent
from PyQt5.QtWidgets import QFileDialog, QHeaderView
from PyQt5.QtGui import QPainter, QBrush, QPen, QColor

from qtvcp.core import Info, Status, Action, Path

INFO = Info()
STATUS = Status()
ACTION = Action()
PATH = Path()

HERE = os.path.dirname(os.path.abspath(__file__))
HELP = os.path.join(PATH.CONFIGPATH, "help_files")
IMAGES = os.path.join(PATH.CONFIGPATH, 'qtdragon/images')
WARNING = 1


class Preview(QtWidgets.QWidget):
    def __init__(self):
        super(Preview, self).__init__()
        self.num_holes = 0
        self.first_angle = 0.0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setBrush(QColor(200, 200, 200, 255))
        painter.drawRect(event.rect())
        self.draw_main_circle(event, painter)
        self.draw_crosshair(event, painter)
        self.draw_holes(event, painter)
        painter.end()        

    def draw_main_circle(self, event, qp):
        size = self.size()
        w = size.width()/2
        h = size.height()/2
        center = QPointF(w, h)
        radius = min(w, h) - 35
        qp.setPen(QPen(Qt.black, 1))
        qp.drawEllipse(center, radius, radius)

    def draw_crosshair(self, event, qp):
        size = self.size()
        cx = int(size.width()/2)
        cy = int(size.height()/2)
        L = min(cx, cy) - 25
        qp.setPen(QPen(Qt.black, 1))
        p1 = QPoint(cx + L, cy)
        p2 = QPoint(cx, cy - L)
        p3 = QPoint(cx - L, cy)
        p4 = QPoint(cx, cy + L)
        qp.drawLine(p1, p3)
        qp.drawLine(p2, p4)
        br1 = QRect(cx + L, cy-6, 30, 12)
        br2 = QRect(cx-15, cy - L - 12, 30, 12)
        br3 = QRect(cx - L - 30, cy-6, 30, 12)
        br4 = QRect(cx-15, cy + L, 30, 12)
        qp.drawText(br1, Qt.AlignHCenter|Qt.AlignVCenter, "0")
        qp.drawText(br2, Qt.AlignHCenter|Qt.AlignVCenter, "90")
        qp.drawText(br3, Qt.AlignHCenter|Qt.AlignVCenter, "180")
        qp.drawText(br4, Qt.AlignHCenter|Qt.AlignVCenter, "270")

    def draw_holes(self, event, qp):
        size = self.size()
        w = size.width()
        h = size.height()
        center = QPointF(w/2, h/2)
        r = (min(w, h) - 70)/2
        qp.setPen(QPen(Qt.red, 2))
        for i in range(self.num_holes):
            if i ==1:
                qp.setPen(QPen(Qt.black, 2))
            theta = ((360.0/self.num_holes) * i) + self.first_angle
            x = r * math.cos(math.radians(theta))
            y = r * math.sin(math.radians(theta))
            x = round(x, 3)
            y = -round(y, 3) # need this to make it go CCW
            p = QPointF(x, y) + center
            qp.drawEllipse(p, 6, 6)

    def set_num_holes(self, num):
        self.num_holes = num

    def set_first_angle(self, angle):
        self.first_angle = angle

class Hole_Circle(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(Hole_Circle, self).__init__()
        self.parent = parent
        self.h = self.parent.parent
        self.dialog_code = 'CALCULATOR'
        self.kbd_code = 'KEYBOARD'
        self.tmpl = '.3f' if INFO.MACHINE_IS_METRIC else '.4f'
        self.helpfile = 'hole_circle_help.html'
        # Load the widgets UI file:
        self.filename = os.path.join(HERE, 'hole_circle.ui')
        try:
            self.instance = uic.loadUi(self.filename, self)
        except AttributeError as e:
            print("Error: ", e)
        self.preview = Preview()
        self.layout_preview.addWidget(self.preview)

        # Initial values
        self._tmp = None
        self.rpm = 0
        self.num_holes = 0
        self.radius = 0
        self.first = 0.0
        self.safe_z = 0
        self.start = 0
        self.depth = 0
        self.drill_feed = 0
        self.min_rpm = INFO.get_safe_int("DISPLAY", "MIN_SPINDLE_0_SPEED")
        self.max_rpm = INFO.get_safe_int("DISPLAY", "MAX_SPINDLE_0_SPEED")
        self.red_border = "border: 2px solid red;"
        self.parm_list = ["spindle", "num_holes", "first", "radius", "safe_z", "start_height", "depth", "drill_feed"]
        # set valid input formats for lineEdits
        self.lineEdit_spindle.setValidator(QtGui.QIntValidator(0, 99999))
        self.lineEdit_num_holes.setValidator(QtGui.QIntValidator(0, 99))
        self.lineEdit_radius.setValidator(QtGui.QDoubleValidator(0, 999, 3))
        self.lineEdit_first.setValidator(QtGui.QDoubleValidator(-999, 999, 3))
        self.lineEdit_safe_z.setValidator(QtGui.QDoubleValidator(0, 99, 3))
        self.lineEdit_start_height.setValidator(QtGui.QDoubleValidator(0, 99, 3))
        self.lineEdit_depth.setValidator(QtGui.QDoubleValidator(0, 99, 3))
        self.lineEdit_drill_feed.setValidator(QtGui.QIntValidator(0, 999))
        # setup event filter to catch focus_in events
        self.event_filter = EventFilter(self)
        for line in self.parm_list:
            self[f'lineEdit_{line}'].installEventFilter(self.event_filter)
        self.lineEdit_comment.installEventFilter(self.event_filter)
        self.event_filter.set_line_list(self.parm_list)
        self.event_filter.set_kbd_list('comment')
        self.event_filter.set_parms(('_hole_circle_', True))
        # setup report table headers
        self.model = QtGui.QStandardItemModel(4, 4)
        self.model.setHorizontalHeaderLabels(['Hole', 'Angle', 'X', 'Y'])
        header = self.report.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        self.report.setModel(self.model)
        # signal connections
        self.chk_units.stateChanged.connect(lambda state: self.units_changed(state))
        self.chk_use_calc.stateChanged.connect(lambda state: self.event_filter.set_dialog_mode(state))
        self.btn_create.clicked.connect(self.create_program)
        self.btn_send.clicked.connect(self.send_program)
        self.btn_help.pressed.connect(self.show_help)

    def _hal_init(self):
        def homed_on_status():
            return (STATUS.machine_is_on() and (STATUS.is_all_homed() or INFO.NO_HOME_REQUIRED))
        STATUS.connect('general', self.dialog_return)
        STATUS.connect('state_off', lambda w: self.setEnabled(False))
        STATUS.connect('state_estop', lambda w: self.setEnabled(False))
        STATUS.connect('interp-idle', lambda w: self.setEnabled(homed_on_status()))
        STATUS.connect('all-homed', lambda w: self.setEnabled(True))
        self.chk_units.setChecked(True)
        self.default_style = self.lineEdit_spindle.styleSheet()

    def dialog_return(self, w, message):
        rtn = message['RETURN']
        name = message.get('NAME')
        obj = message.get('OBJECT')
        code = bool(message.get('ID') == '_hole_circle_')
        next = message.get('NEXT', False)
        back = message.get('BACK', False)
        if code and name == self.dialog_code:
            obj.setStyleSheet(self.default_style)
            if rtn is not None:
                if obj.objectName().replace('lineEdit_', '') in ['spindle', 'num_holes', 'drill_feed']:
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

    def units_changed(self, mode):
        text = "MM" if mode else "IN"
        chk_text = "METRIC" if mode else "IMPERIAL"
        self.chk_units.setText(chk_text)
        self.lbl_radius_unit.setText(text)
        self.lbl_safe_z_unit.setText(text)
        self.lbl_start_height_unit.setText(text)
        self.lbl_depth_unit.setText(text)
        self.lbl_drill_feed_unit.setText(text + '/MIN')

    def validate(self):
        valid = True
        blank = "Input field cannot be blank"
        for item in self.parm_list:
            self['lineEdit_' + item].setStyleSheet(self.default_style)
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

        try:
            self.num_holes = int(self.lineEdit_num_holes.text())
            if self.num_holes <= 0:
                self.h.add_status("Number of holes must be > 0", WARNING)
                self.lineEdit_num_holes.setStyleSheet(self.red_border)
                valid = False
        except:
            self.h.add_status(blank, WARNING)
            self.lineEdit_num_holes.setStyleSheet(self.red_border)
            valid = False

        try:
            self.radius = float(self.lineEdit_radius.text())
            if self.radius <= 0.0:
                self.h.add_status("Circle radius must be > 0", WARNING)
                self.lineEdit_radius.setStyleSheet(self.red_border)
                valid = False
        except:
            self.h.add_status(blank, WARNING)
            self.lineEdit_radius.setStyleSheet(self.red_border)
            valid = False

        try:
            self.first = float(self.lineEdit_first.text())
            if self.first >= 360.0:
                self.h.add_status("Angle of first hole must be < 360", WARNING)
                self.lineEdit_first.setStyleSheet(self.red_border)
                valid = False
        except:
            self.h.add_status(blank, WARNING)
            self.lineEdit_first.setStyleSheet(self.red_border)
            valid = False

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

        try:
            self.start = float(self.lineEdit_start_height.text())
            if self.start < 0.0 or self.start > self.safe_z:
                self.h.add_status(f"Start height must be between 0 and {self.safe_z}", WARNING)
                self.lineEdit_start_height.setStyleSheet(self.red_border)
                valid = False
        except:
            self.h.add_status(blank, WARNING)
            self.lineEdit_start_height.setStyleSheet(self.red_border)
            valid = False

        try:
            self.depth = float(self.lineEdit_depth.text())
            if self.depth <= 0.0:
                self.h.add_status("Drill depth must be > 0", WARNING)
                self.lineEdit_depth.setStyleSheet(self.red_border)
                valid = False
        except:
            self.h.add_status(blank, WARNING)
            self.lineEdit_depth.setStyleSheet(self.red_border)
            valid = False

        try:
            self.drill_feed = float(self.lineEdit_drill_feed.text())
            if self.drill_feed <= 0.0:
                self.h.add_status("Drill feedrate must be > 0", WARNING)
                self.lineEdit_drill_feed.setStyleSheet(self.red_border)
                valid = False
        except:
            self.h.add_status(blank, WARNING)
            self.lineEdit_drill_feed.setStyleSheet(self.red_border)
            valid = False
        return valid

    def create_program(self):
        if not self.validate(): return
        self.show_preview()
        self.clear_model()
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        fileName, _ = QFileDialog.getSaveFileName(self,"Save to file","","All Files (*);;ngc Files (*.ngc)", options=options)
        if fileName:
            self.calculate_toolpath(fileName)
            self.h.add_status(f"Program successfully saved to {fileName}")
        else:
            self.h.add_status("Program creation aborted")

    def send_program(self):
        if not self.validate(): return
        self.show_preview()
        self.clear_model()
        filename = self.make_temp()
        self.calculate_toolpath(filename)
        ACTION.OPEN_PROGRAM(filename)
        self.h.add_status("Program successfully sent to Linuxcnc")

    def calculate_toolpath(self, fname):
        comment = self.lineEdit_comment.text()
        unit_code = 'G21' if self.chk_units.isChecked() else 'G20'
        units_text = 'Metric' if self.chk_units.isChecked() else 'Imperial'
        self.line_num = 5
        self.file = open(fname, 'w')
        # opening preamble
        self.file.write("%\n")
        self.file.write(f"({comment})\n")
        self.file.write(f"({self.num_holes} Holes on {self.radius *2} Diameter)\n")
        self.file.write(f"(**NOTE - All units are {units_text})\n")
        self.file.write("(XY origin at circle center)\n")
        self.file.write("(Z origin at top face of surface)\n")
        self.file.write("\n")
        self.next_line("G40 G49 G64 P0.03")
        self.next_line("G17")
        self.next_line(unit_code)
        if self.chk_mist.isChecked():
            self.next_line("M7")
        if self.chk_flood.isChecked():
            self.next_line("M8")
        self.next_line(f"G0 Z{self.safe_z}")
        self.next_line("G0 X0.0 Y0.0")
        self.next_line(f"S{self.rpm} M3")
        # main section
        row = 0
        for i in range(self.num_holes):
            col = 0
            next_angle = ((360.0/self.num_holes) * i) + self.first
            next_angle = round(next_angle, 3)
            next_x = self.radius * math.cos(math.radians(next_angle))
            next_y = self.radius * math.sin(math.radians(next_angle))
            item = QtGui.QStandardItem(str(i))
            self.model.setItem(row, col, item)
            col += 1
            item = QtGui.QStandardItem(f'{next_angle:8.3f}')
            self.model.setItem(row, col, item)
            col += 1
            item = QtGui.QStandardItem(f'{next_x:8.3f}')
            self.model.setItem(row, col, item)
            col += 1
            item = QtGui.QStandardItem(f'{next_y:8.3f}')
            self.model.setItem(row, col, item)
            row += 1
            self.next_line(f"G0 @{self.radius} ^{next_angle}")
            self.next_line(f"Z{self.start}")
            self.next_line(f"G1 Z-{self.depth} F{self.drill_feed}")
            self.next_line(f"G0 Z{self.safe_z}")
        # closing section
        self.next_line("G0 X0.0 Y0.0")
        self.next_line("M9")
        self.next_line("M5")
        self.next_line("M2")
        self.file.write("%\n")
        self.file.close()

    def show_help(self):
        fname = os.path.join(HELP, self.helpfile)
        self.parent.show_help_page(fname)

    def show_preview(self):
        self.preview.set_num_holes(self.num_holes)
        self.preview.set_first_angle(self.first)
        self.preview.update()
        
    def make_temp(self):
        fd, path = tempfile.mkstemp(prefix='hole_circle', suffix='.ngc')
        atexit.register(lambda: os.remove(path))
        return path

    def next_line(self, text):
        self.file.write(f"N{self.line_num} " + text + "\n")
        self.line_num += 5

    def clear_model(self):
        self.model.removeRows(0, self.model.rowCount())
        self.model.setRowCount(self.num_holes)

    # required code for subscriptable objects
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)

    w = Hole_Circle()
    w.show()
    sys.exit( app.exec_() )

