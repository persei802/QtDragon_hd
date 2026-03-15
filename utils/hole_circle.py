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
from PyQt5.QtCore import QPoint, QPointF, QLine, QRect, QRectF, Qt, QEvent, pyqtSignal
from PyQt5.QtWidgets import QWidget, QLineEdit
from PyQt5.QtGui import QStandardItem, QStandardItemModel, QIntValidator, QDoubleValidator, QPainter, QPen, QColor

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
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.num_holes = 0
        self.first_angle = 0.0

    def paintEvent(self, event):
        painter = QPainter(self)
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
        qp.setPen(QPen(Qt.white, 1))
        qp.drawEllipse(center, radius, radius)

    def draw_crosshair(self, event, qp):
        size = self.size()
        cx = int(size.width()/2)
        cy = int(size.height()/2)
        L = 30
        qp.setPen(QPen(Qt.white, 1))
        p1 = QPoint(cx + L, cy)
        p2 = QPoint(cx, cy - L)
        p3 = QPoint(cx - L, cy)
        p4 = QPoint(cx, cy + L)
        qp.drawLine(p1, p3)
        qp.drawLine(p2, p4)

    def draw_holes(self, event, qp):
        size = self.size()
        w = size.width()
        h = size.height()
        center = QPointF(w/2, h/2)
        r = (min(w, h) - 70)/2
        qp.setPen(QPen(Qt.yellow, 1))
        for i in range(self.num_holes):
            theta = ((360.0/self.num_holes) * i) + self.first_angle
            x = r * math.cos(math.radians(theta))
            y = r * math.sin(math.radians(theta))
            x = round(x, 3)
            y = -round(y, 3) # need this to make it go CCW
            p = QPointF(x, y) + center
            qp.drawEllipse(p, 20, 20)
            rc = r + 30
            xc = rc * math.cos(math.radians(theta))
            xc = round(xc, 3)
            yc = rc * math.sin(math.radians(theta))
            yc = -round(yc, 3)
            rect = QRectF(0, 0, 30, 20)
            pc = QPointF(xc, yc)
            pt = QPointF(xc - 15, yc -10) + center
            rect.moveTo(pt)
            qp.drawText(rect, Qt.AlignCenter, str(i))

    def set_num_holes(self, num):
        self.num_holes = num

    def set_first_angle(self, angle):
        self.first_angle = angle

class Hole_Report(QWidget):
    hole_selected = pyqtSignal(tuple)
    def __init__(self, table, parent=None):
        super(Hole_Report, self).__init__()
        self.table = table
        self.model = QStandardItemModel(4, 4)
        self.model.setHorizontalHeaderLabels(['Hole', 'Angle', 'X', 'Y'])
        self.table.setModel(self.model)
        self.table.clicked.connect(self.table_clicked)

    def add_row(self, row, angle, x, y):
        item_0 = QStandardItem(str(row))
        item_1 = QStandardItem(f'{angle:.3f}')
        item_2 = QStandardItem(f'{x:.3f}')
        item_3 = QStandardItem(f'{y:.3f}')
        for i, item in enumerate([item_0, item_1, item_2, item_3]):
            item.setEditable(False)
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            item.setSelectable(False)
            self.model.setItem(row, i, item)

    def table_clicked(self, index):
        if index.column() != 0: return
        hole = int(index.data())
        x = float(self.model.item(hole, 2).text())
        y = float(self.model.item(hole, 3).text())
        self.hole_selected.emit((hole, x, y))


class Hole_Circle(QWidget, Common):
    def __init__(self, parent=None):
        super(Hole_Circle, self).__init__()
        self.parent = parent
        self.h = self.parent.parent
        self.geometry = None
        self.tmpl = '.3f' if INFO.MACHINE_IS_METRIC else '.4f'
        self.helpfile = 'hole_circle_help.html'
        self.mdi_cmd = ''
        self.hole_list = list()
        self.settings = []
        # Load the widgets UI file:
        self.filename = os.path.join(HERE, 'hole_circle.ui')
        try:
            self.instance = uic.loadUi(self.filename, self)
        except AttributeError as e:
            print("Error: ", e)
        self.preview = Preview()
        self.layout_preview.addWidget(self.preview)
        self.report = Hole_Report(self.table_hole_circle)
        self.btn_goto_hole.setEnabled(False)
        self.set_unit_labels()
        # list of input fields
        self.float_inputs = ['center_x', 'center_y', 'first', 'radius', 'safe_z', 'depth', 'retract', 'peck', 'dwell']
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
        self.lineEdit_depth.setValidator(QDoubleValidator(0, 99, 3))
        self.lineEdit_retract.setValidator(QDoubleValidator(0, 99, 3))
        self.lineEdit_peck.setValidator(QDoubleValidator(0, 99, 3))
        self.lineEdit_dwell.setValidator(QDoubleValidator(0, 99, 3))
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
        # signal connections
        self.chk_use_calc.stateChanged.connect(lambda state: self.event_filter.set_dialog_mode(state))
        self.btn_save.pressed.connect(self.save_program)
        self.btn_send.pressed.connect(self.send_program)
        self.btn_help.pressed.connect(self.show_help)
        self.btn_goto_hole.pressed.connect(self.goto_hole)
        self.report.hole_selected.connect(self.hole_selected)
        self.tabWidget_hole_circle.currentChanged.connect(lambda index: self.btn_goto_hole.setEnabled(index))

    def _hal_init(self):
        def homed_on_status():
            return (STATUS.machine_is_on() and (STATUS.is_all_homed() or INFO.NO_HOME_REQUIRED))
        STATUS.connect('general', self.dialog_return)
        STATUS.connect('state_off', lambda w: self.setEnabled(False))
        STATUS.connect('state_estop', lambda w: self.setEnabled(False))
        STATUS.connect('interp-idle', lambda w: self.setEnabled(homed_on_status()))
        STATUS.connect('all-homed', lambda w: self.setEnabled(True))
        self.default_style = self.lineEdit_spindle.styleSheet()

        if self.parent.w.PREFS_:
            self.settings = self.gbox_parameters.findChildren(QLineEdit)
            for item in self.settings:
                item.setText(self.parent.w.PREFS_.getpref(item.objectName(), '10', str, 'HOLE_CIRCLE_OPTIONS'))

    def closing_cleanup__(self):
        if self.parent.w.PREFS_:
            for item in self.settings:
                self.parent.w.PREFS_.putpref(item.objectName(), item.text(), str, 'HOLE_CIRCLE_OPTIONS')

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

    def set_unit_labels(self):
        text = "MM" if INFO.MACHINE_IS_METRIC else "IN"
        self.lbl_center_unit.setText(text)
        self.lbl_radius_unit.setText(text)
        self.lbl_safe_z_unit.setText(text)
        self.lbl_depth_unit.setText(text)
        self.lbl_retract_unit.setText(text)
        self.lbl_peck_unit.setText(text)
        self.lbl_drill_feed_unit.setText(text + '/MIN')

    def save_program(self):
        if not self.validate(): return
        self.generate_holes()
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
        self.generate_holes()
        self.calculate_program()
        filename = self.make_temp('hole_circle')
        with open(filename, 'w') as f:
            f.write('\n'.join(self.gcode))
        ACTION.OPEN_PROGRAM(filename)
        self.h.add_status("Program sent to Linuxcnc")

    def calculate_program(self):
        self.gcode = []
        comment = self.lineEdit_comment.text()
        unit_code = 'G21' if INFO.MACHINE_IS_METRIC else 'G20'
        units_text = 'Metric' if INFO.MACHINE_IS_METRIC else 'Imperial'
        self.line_num = 5
        # opening preamble
        self.gcode.append('%')
        self.gcode.append(f'({comment})')
        self.gcode.append(f'({self.num_holes} Holes on {self.radius * 2} Diameter)')
        self.gcode.append(f'(**NOTE - All units are {units_text})')
        self.gcode.append(f'(Circle origin at X{self.center_x} Y{self.center_y})')
        self.gcode.append('(Z origin at top of workpiece)')
        self.next_line('G40 G49 G64 P0.03')
        self.next_line('G17')
        self.next_line(unit_code)
        if self.chk_mist.isChecked():
            self.next_line('M7')
        if self.chk_flood.isChecked():
            self.next_line('M8')
        self.next_line(f'M6 T{self.tool}')
        self.next_line(f'G0 Z{self.safe_z}')
        if self.chk_use_tlo.isChecked():
            self.next_line('G43')
        self.next_line(f'S{self.spindle} M3')
        self.next_line(f'G0 X{self.hole_list[0][0]:.3f} Y{self.hole_list[0][1]:.3f}')
        self.next_line(f'G0 Z{self.retract}')
        # main section
        if self.chk_g83.isChecked():
            self.next_line(f'G98 G83 R{self.retract} Z-{self.depth} Q{self.peck} F{self.drill_feed}')
        elif self.chk_g82.isChecked():
            self.next_line(f'G98 G82 R{self.retract} Z-{self.depth} P{self.dwell} F{self.drill_feed}')
        else:
            self.next_line(f'G98 G81 R{self.retract} Z-{self.depth} F{self.drill_feed}')
        for i in range(1, self.num_holes):
            self.next_line(f'X{self.hole_list[i][0]:.3f} Y{self.hole_list[i][1]:.3f}')
        self.next_line('G80')
        # closing section - return to circle center
        self.next_line(f'G0 Z{self.safe_z}')
        self.next_line(f'G0 X{self.center_x} Y{self.center_y}')
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
        if not (0.0 <= self.retract <= self.safe_z):
            self.lineEdit_retract.setStyleSheet(self.red_border)
            self.h.add_status(f'Drill retract height must be between 0.0 and {self.safe_z}', WARNING)
            return False
        # show preview
        self.preview.set_num_holes(self.num_holes)
        self.preview.set_first_angle(self.first)
        self.preview.update()
        return True

    def generate_holes(self):
        self.report.model.setRowCount(0)
        self.hole_list.clear()
        for i in range(self.num_holes):
            next_angle = ((360.0 / self.num_holes) * i) + self.first
            next_x = self.radius * math.cos(math.radians(next_angle)) + self.center_x
            next_y = self.radius * math.sin(math.radians(next_angle)) + self.center_y
            self.report.add_row(i, next_angle, next_x, next_y)
            self.hole_list.append((next_x, next_y))

    def hole_selected(self, hole):
        num, x, y = hole
        self.btn_goto_hole.setText(f'GO TO HOLE {num}')
        self.btn_goto_hole.setProperty('pos_x', x)
        self.btn_goto_hole.setProperty('pos_y', y)

    def goto_hole(self):
        x = self.btn_goto_hole.property('pos_x')
        y = self.btn_goto_hole.property('pos_y')
        ACTION.CALL_MDI('G53 G0 Z0')
        ACTION.CALL_MDI(f'G90 G0 X{x} Y{y}')

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

    w = Hole_Circle()
    w.show()
    sys.exit( app.exec_() )

