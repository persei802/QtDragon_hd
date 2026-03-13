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

from lib.event_filter import EventFilter
from utils.utils_mixin import Common

from PyQt5 import uic
from PyQt5.QtCore import QPoint, QPointF, QLine, QRect, QFile, Qt, QEvent
from PyQt5.QtWidgets import QWidget, QFileDialog, QLineEdit, QHeaderView
from PyQt5.QtGui import QStandardItem, QStandardItemModel, QIntValidator, QDoubleValidator, QPainter, QBrush, QPen, QColor

from qtvcp.core import Info, Status, Action, Path

INFO = Info()
STATUS = Status()
ACTION = Action()
PATH = Path()

HERE = os.path.dirname(os.path.abspath(__file__))
HELP = os.path.join(PATH.CONFIGPATH, "help_files")
WARNING = 1


class Preview(QWidget):
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
            if i == 1:
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

class Hole_Circle(QWidget, Common):
    def __init__(self, parent=None):
        super(Hole_Circle, self).__init__()
        self.parent = parent
        self.h = self.parent.parent
        self.geometry = None
        self.tmpl = '.3f' if INFO.MACHINE_IS_METRIC else '.4f'
        self.helpfile = 'hole_circle_help.html'
        self.mdi_cmd = ''
        # Load the widgets UI file:
        self.filename = os.path.join(HERE, 'hole_circle.ui')
        try:
            self.instance = uic.loadUi(self.filename, self)
        except AttributeError as e:
            print("Error: ", e)
        self.preview = Preview()
        self.layout_preview.addWidget(self.preview)

        # list of input fields
        self.float_inputs = ['center_x', 'center_y', 'first', 'radius', 'safe_z', 'start', 'depth']
        self.int_inputs = ['tool', 'num_holes', 'drill_feed', 'spindle']

        # set valid input formats for lineEdits
        self.lineEdit_tool.setValidator(QIntValidator(1, 99999))
        self.lineEdit_num_holes.setValidator(QIntValidator(0, 99))
        self.lineEdit_spindle.setValidator(QIntValidator(0, 99999))
        self.lineEdit_drill_feed.setValidator(QIntValidator(0, 999))
        self.lineEdit_center_x.setValidator(QDoubleValidator(-999, 999, 3))
        self.lineEdit_center_y.setValidator(QDoubleValidator(-999, 999, 3))
        self.lineEdit_radius.setValidator(QDoubleValidator(0, 999, 3))
        self.lineEdit_first.setValidator(QDoubleValidator(0, 999, 3))
        self.lineEdit_safe_z.setValidator(QDoubleValidator(0, 999, 3))
        self.lineEdit_start.setValidator(QDoubleValidator(0, 99, 3))
        self.lineEdit_depth.setValidator(QDoubleValidator(0, 99, 3))
        # setup event filter to catch focus_in events
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
        self.event_filter.set_parms(('_hole_circle_', True))
        self.event_filter.set_tool_list('tool')
        # setup report table headers
        self.model = QStandardItemModel(4, 4)
        self.model.setHorizontalHeaderLabels(['Hole', 'Angle', 'X', 'Y'])
        header = self.report.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        self.report.setModel(self.model)
        # signal connections
        self.chk_units.stateChanged.connect(lambda state: self.units_changed(state))
        self.chk_use_calc.stateChanged.connect(lambda state: self.event_filter.set_dialog_mode(state))
        self.btn_save.pressed.connect(self.save_program)
        self.btn_send.pressed.connect(self.send_program)
        self.btn_help.pressed.connect(self.show_help)
        self.btn_goto_hole.pressed.connect(self.goto_hole)
        self.report.clicked.connect(self.table_clicked)

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
        elif code and name == self.tool_code:
            if rtn is not None:
                obj.setText(str(int(rtn)))

    def units_changed(self, mode):
        text = "MM" if mode else "IN"
        chk_text = "METRIC" if mode else "IMPERIAL"
        self.chk_units.setText(chk_text)
        self.lbl_center_unit.setText(text)
        self.lbl_radius_unit.setText(text)
        self.lbl_safe_z_unit.setText(text)
        self.lbl_start_unit.setText(text)
        self.lbl_depth_unit.setText(text)
        self.lbl_drill_feed_unit.setText(text + '/MIN')

    def save_program(self):
        if not self.validate(): return
        self.calculate_program()
        caption = 'Save Hole Circle Program'
        _dir = os.path.expanduser('~/linuxcnc/nc_files')
        _filter = 'ngc Files (*.ngc)'
        fileName, _ = self.save_program_file(self, caption, _dir, _filter)
        if fileName:
            if self.gcode:
                with open(fileName, 'w') as f:
                    f.write('\n'.join(self.gcode))
                self.h.add_status(f"Program successfully saved to {fileName}")
        else:
            self.h.add_status("Program save cancelled", WARNING)

    def send_program(self):
        if not self.validate(): return
        self.calculate_program()
        filename = self.make_temp('hole_circle')
        with open(filename, 'w') as f:
            f.write('\n'.join(self.gcode))
        ACTION.OPEN_PROGRAM(filename)
        self.h.add_status("Program sent to Linuxcnc")

    def calculate_program(self):
        self.gcode = []
        self.model.setRowCount(self.num_holes)
        comment = self.lineEdit_comment.text()
        unit_code = 'G21' if self.chk_units.isChecked() else 'G20'
        units_text = 'Metric' if self.chk_units.isChecked() else 'Imperial'
        self.line_num = 5
        # opening preamble
        self.gcode.append("%")
        self.gcode.append(f"({comment})")
        self.gcode.append(f"({self.num_holes} Holes on {self.radius * 2} Diameter)")
        self.gcode.append(f"(**NOTE - All units are {units_text})")
        self.gcode.append(f"(Circle origin at X{self.center_x} Y{self.center_y})")
        self.gcode.append("(Z origin at top face of surface)\n")
        self.next_line("G40 G49 G64 P0.03")
        self.next_line("G17")
        self.next_line(unit_code)
        if self.chk_mist.isChecked():
            self.next_line("M7")
        if self.chk_flood.isChecked():
            self.next_line("M8")
        self.next_line(f'M6 T{self.tool}')
        self.next_line(f"G0 Z{self.safe_z}")
        self.next_line(f"G0 X{self.center_x} Y{self.center_y}")
        self.next_line(f"S{self.spindle} M3")
        # main section
        row = 0
        for i in range(self.num_holes):
            col = 0
            next_angle = ((360.0/self.num_holes) * i) + self.first
            next_angle = round(next_angle, 3)
            next_x = self.radius * math.cos(math.radians(next_angle)) + self.center_x
            next_y = self.radius * math.sin(math.radians(next_angle)) + self.center_y
            item = QStandardItem(str(i))
            self.model.setItem(row, col, item)
            col += 1
            item = QStandardItem(f'{next_angle:8.3f}')
            self.model.setItem(row, col, item)
            col += 1
            item = QStandardItem(f'{next_x:8.3f}')
            self.model.setItem(row, col, item)
            col += 1
            item = QStandardItem(f'{next_y:8.3f}')
            self.model.setItem(row, col, item)
            row += 1
            self.next_line(f"G0 X{next_x:.3f} Y{next_y:.3f}")
            self.next_line(f"Z{self.start}")
            self.next_line(f"G1 Z-{self.depth} F{self.drill_feed}")
            self.next_line(f"G0 Z{self.safe_z}")
        # closing section - return to circle center
        self.next_line(f"G0 X{self.center_x} Y{self.center_y}")
        self.post_amble()

    def show_help(self):
        fname = os.path.join(HELP, self.helpfile)
        self.parent.show_help_page(fname)
       
    def validate(self):
        if not self.check_float_blanks(self.float_inputs): return False
        if not self.check_int_blanks(self.int_inputs): return False
        # additional checks
        for val in self.float_inputs[-4:]:
            if self[val] <= 0.0:
                self[f'lineEdit_{val}'].setStyleSheet(self.red_border)
                self.h.add_status(f'{val} must be > 0', WARNING)
                return False
        for val in ['num_holes', 'drill_feed']:
            if self[val] <= 0:
                self[f'lineEdit_{val}'].setStyleSheet(self.red_border)
                self.h.add_status(f'{val} must be > 0', WARNING)
                return False
        if not (self.min_rpm <= self.spindle <= self.max_rpm):
            self.lineEdit_spindle.setStyleSheet(self.red_border)
            self.h.add_status(f'Spindle RPM must be between {self.min_rpm} and {self.max_rpm}', WARNING)
            return False
        if not (0.0 <= self.start <= self.safe_z):
            self.lineEdit_start.setStyleSheet(self.red_border)
            self.h.add_status(f'Drill start height must be between 0.0 and {self.safe_z}', WARNING)
            return False
        # show preview
        self.model.setRowCount(0)
        self.preview.set_num_holes(self.num_holes)
        self.preview.set_first_angle(self.first)
        self.preview.update()
        return True

    def table_clicked(self, index):
        if index.column() > 0: return
        row = index.row()
        idx = self.model.indexFromItem(self.model.item(row, 2))
        idy = self.model.indexFromItem(self.model.item(row, 3))
        x = idx.data()
        y = idy.data()
        self.btn_goto_hole.setText(f'GO TO HOLE {row}')
        self.mdi_cmd = f"G90 G0 X{x} Y{y}"

    def goto_hole(self):
        if self.model.rowCount() == 0: return
        ACTION.CALL_MDI_WAIT(f'G90 G0 Z{self.safe_z}', 5, mode_return=True)
        ACTION.CALL_MDI_WAIT(self.mdi_cmd, 10, mode_return=True)

    def next_line(self, text):
        self.gcode.append(f"N{self.line_num} {text}")
        self.line_num += 5

    def clear_model(self):
        self.model.removeRows(0, self.model.rowCount())
        self.model.setRowCount(0)

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

