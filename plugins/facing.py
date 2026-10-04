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
import os

from qtpy import uic
from qtpy.QtGui import QIntValidator, QDoubleValidator, QPen, QBrush, QColor, QPainterPath
from qtpy.QtCore import Qt, QPointF, QLineF, QSettings
from qtpy.QtWidgets import QWidget, QGraphicsScene

from qtvcp.core import Info, Status, Action, Path, Tool
from qtvcp import logger

from lib.event_filter import EventFilter
from plugins.utils_mixin import Common

LOG = logger.getLogger(__name__)
LOG.setLevel(logger.INFO) # One of DEBUG, INFO, WARNING, ERROR, CRITICAL
INFO = Info()
STATUS = Status()
ACTION = Action()
PATH = Path()
TOOL = Tool()
HERE = os.path.dirname(os.path.abspath(__file__))
HELP = os.path.join(PATH.CONFIGPATH, "help_files")
WARNING = 1
ERROR = 2

PLUGIN_INFO = {
    'mod_name' : 'facing',
    'class_name' : 'Facing',
    'item_text' : 'FACING',
    'version' : '2.0',
    'description' : '''Facing operation GCode generator
Create toolpaths for rastering along X or Y axis
Create toolpaths at 45 deg raster angle
'''
}


class Facing(QWidget, Common):
    def __init__(self, parent=None):
        super(Facing, self).__init__()
        self.parent = parent
        self.settings = QSettings(os.path.join(HERE, 'settings.ini'), QSettings.IniFormat)
        self.calculate_pass = None
        self.helpfile = os.path.join(HELP, 'facing_help.html')
        self.default_style = ''
        self.tmpl = '.3f' if INFO.MACHINE_IS_METRIC else '.4f'
        # Load the widgets UI file:
        self.filename = os.path.join(HERE, 'facing.ui')
        try:
            self.instance = uic.loadUi(self.filename, self)
        except AttributeError as e:
            self.parent.add_status(e, WARNING)

        self.float_inputs = ['diameter', 'size_x', 'size_y', 'stepover', 'stepdown', 'safe_z', 'start_z', 'last_z']
        self.int_inputs = ['tool', 'xy_feedrate', 'z_feedrate', 'spindle']

        # set valid input formats for lineEdits
        self.lineEdit_tool.setValidator(QIntValidator(1, 99))
        self.lineEdit_diameter.setValidator(QDoubleValidator(0, 999, 3))
        self.lineEdit_spindle.setValidator(QIntValidator(0, 99999))
        self.lineEdit_xy_feedrate.setValidator(QIntValidator(0, 9999))
        self.lineEdit_z_feedrate.setValidator(QIntValidator(0, 9999))
        self.lineEdit_safe_z.setValidator(QDoubleValidator(0, 9999, 3))
        self.lineEdit_start_z.setValidator(QDoubleValidator(-9999, 9999, 3))
        self.lineEdit_last_z.setValidator(QDoubleValidator(-9999, 9999, 3))
        self.lineEdit_stepover.setValidator(QDoubleValidator(0, 99, 3))
        self.lineEdit_stepdown.setValidator(QDoubleValidator(0, 99, 3))
        self.lineEdit_size_x.setValidator(QDoubleValidator(0, 9999, 3))
        self.lineEdit_size_y.setValidator(QDoubleValidator(0, 9999, 3))

        # setup event filters to catch focus_in events
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
        self.event_filter.set_tool_list('tool')
        self.event_filter.set_parms(('_facing_', True))

        # setup graphics preview
        self.scene = QGraphicsScene()
        self.facing_preview.setScene(self.scene)
        self.facing_preview.scale(1, -1)
        self.path = QPainterPath()
        self.pen = QPen(Qt.yellow)
        self.pen.setWidth(2)
        self.pen.setCosmetic(True)

        # signal connections
        self.chk_use_calc.stateChanged.connect(lambda state: self.event_filter.set_dialog_mode(state))
        self.lineEdit_tool.editingFinished.connect(self.load_tool)
        self.btn_preview.pressed.connect(lambda: self.create_program('preview'))
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
            self[f'lineEdit_{line}'].setText(self.settings.value(f'facing/{line}', '0', str))
        for line in self.float_inputs:
            self[f'lineEdit_{line}'].setText(self.settings.value(f'facing/{line}', '0', str))

    def closing_cleanup__(self):
        for line in self.int_inputs:
            self.settings.setValue(f'facing/{line}', self[f'lineEdit_{line}'].text())
        for line in self.float_inputs:
            self.settings.setValue(f'facing/{line}', self[f'lineEdit_{line}'].text())
        self.settings.sync()

    def dialog_return(self, w, message):
        rtn = message['RETURN']
        name = message.get('NAME')
        obj = message.get('OBJECT')
        code = bool(message.get('ID') == '_facing_')
        next = message.get('NEXT', False)
        back = message.get('BACK', False)
        if code and name == self.dialog_code:
            obj.setStyleSheet(self.default_style)
            if rtn is not None:
                if obj.objectName().replace('lineEdit_', '') in ['spindle', 'xy_feedrate', 'z_feedrate']:
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

    def set_unit_labels(self):
        unit = "MM" if state else "IN"
        self.lbl_feed_xy_unit.setText(unit + "/MIN")
        self.lbl_feed_z_unit.setText(unit + "/MIN")
        for val in ['diameter', 'safe_z', 'first', 'last', 'stepover', 'stepdown', 'size']:
            self[f'lbl_{val}_unit'].setText(unit)

    def validate(self):
        if not self.check_float_blanks(self.float_inputs): return False
        if not self.check_int_blanks(self.int_inputs): return False
        # additional checks
        for val in self.float_inputs[:-2]:
            if self[val] <= 0.0:
                self[f'lineEdit_{val}'].setStyleSheet(self.red_border)
                self.parent.add_status(f'{val} must be > 0', WARNING)
                return False
        max_width = self.max_x - self.min_x
        max_height = self.max_y - self.min_y
        if self.size_x > max_width:
            self.lineEdit_size_x.setStyleSheet(self.red_border)
            self.parent.add_status(f'Size of X must be < {max_width}', WARNING)
            return False
        if self.size_y > max_height:
            self.lineEdit_size_y.setStyleSheet(self.red_border)
            self.parent.add_status(f'Size of Y must be < {max_height}', WARNING)
            return False
        for val in ['xy_feedrate', 'z_feedrate']:
            if self[val] <= 0:
                self[f'lineEdit_{val}'].setStyleSheet(self.red_border)
                self.parent.add_status(f'{val} must be > 0', WARNING)
                return False
        if self.xy_feedrate > self.max_feed:
            self.lineEdit_xy_feed.setStyleSheet(self.red_border)
            self.parent.add_status(f'Feedrate must be less than {self.max_feed}', WARNING)
            return False
        if self.last_z > self.start_z:
            self.lineEdit_last_z.setStyleSheet(self.red_border)
            self.parent.add_status('Start height must be greater than last height', WARNING)
            return False
        if self.stepover > self.diameter:
            self.lineEdit_stepover.setStyleSheet(self.red_border)
            self.parent.add_status('Stepover must be less than tool diameter', WARNING)
            return False
        if not (self.min_rpm <= self.spindle <= self.max_rpm):
            self.lineEdit_spindle.setStyleSheet(self.red_border)
            self.parent.add_status(f'Spindle RPM must be between {self.min_rpm} and {self.max_rpm}', WARNING)
            return False
        return True

    def create_program(self, mode):
        if not self.validate(): return
        if mode == 'preview':
            self.update_preview()
            return
        if not self.calculate_gcode():
            self.parent.add_status('Unable to calculate gcode', ERROR)
            return
        if mode == 'send':
            filename = self.make_temp('facing')
            if self.gcode:
                self.update_preview()
                with open(filename, 'w') as f:
                    f.write('\n'.join(self.gcode))
                ACTION.OPEN_PROGRAM(filename)
                self.parent.add_status("Program sent to Linuxcnc")
            else:
                self.parent.add_status("No gcode data to save", WARNING)
        elif mode == 'save':
            caption = 'Save Facing Program'
            _dir = os.path.expanduser('~/linuxcnc/nc_files')
            _filter = 'ngc Files (*.ngc)'
            fileName, _ = self.save_program_file(self, caption, _dir, _filter)
            if fileName:
                if self.gcode:
                    self.update_preview()
                    with open(fileName, 'w') as f:
                        f.write('\n'.join(self.gcode))
                    self.parent.add_status(f"Program saved to {fileName}")
                else:
                    self.parent.add_status("No gcode data to save", WARNING)
            else:
                self.parent.add_status("Program save cancelled")

    def load_tool(self, tool=None):
        if tool is None:
            tool = int(self.lineEdit_tool.text())
        info = TOOL.GET_TOOL_INFO(tool)
        if info:
            self.lineEdit_diameter.setText(str(info[11]))
            self.lineEdit_tool_info.setText(info[15])

    def calculate_gcode(self):
        self.gcode = []
        passes = 0
        comment = self.lineEdit_comment.text()
        unit_code = 'G21' if INFO.MACHINE_IS_METRIC else 'G20'
        units_text = 'Metric' if INFO.MACHINE_IS_METRIC else 'Imperial'
        # opening preamble
        self.gcode.append("%")
        self.gcode.append(f"({comment})")
        self.gcode.append(f"(**NOTE - All units are {units_text})")
        self.gcode.append(f"(Area: X {self.size_x} by Y {self.size_y})")
        self.gcode.append(f"(Tool Diameter {self.diameter} with Stepover {self.stepover})\n")
        self.gcode.append(f"G40 G49 G64 P0.03 M6 T{self.tool}")
        self.gcode.append("G17")
        self.gcode.append(unit_code)
        if self.chk_mist.isChecked():
            self.gcode.append("M7")
        if self.chk_flood.isChecked():
            self.gcode.append("M8")
        self.gcode.append(f"S{self.spindle} M3")
        if self.rbtn_raster_0.isChecked():
            self.calculate_pass = self.raster_0
        elif self.rbtn_raster_45.isChecked():
            self.calculate_pass = self.raster_45
        elif self.rbtn_raster_90.isChecked():
            self.calculate_pass = self.raster_90
        else:
            self.gcode.append("(Unable to determine raster direction)")
            return False
        zlevel = self.start_z
        last_pass = False
        # start facing passes
        while True:
            passes += 1
            self.gcode.append(f"(Pass {passes})")
            if zlevel <= self.last_z:
                zlevel = self.last_z
                last_pass = True
            self.gcode.append(f"G0 Z{self.safe_z}")
            self.gcode.append("G0 X0.0 Y0.0")
            self.gcode.append(f"G1 Z{zlevel:.3f} F{self.z_feedrate}")
            self.calculate_pass()
            if last_pass is True: break
            zlevel -= self.stepdown
        # final profile
        if self.chk_profile.isChecked():
            self.gcode.append("(Profile pass)")
            self.gcode.append(f"G0 Z{self.safe_z}")
            self.gcode.append("G0 X0.0 Y0.0")
            self.gcode.append(f"G1 Z{self.last_z} F{self.z_feedrate}")
            self.gcode.append(f"G1 X{self.size_x} F{self.xy_feedrate}")
            self.gcode.append(f"G1 Y{self.size_y}")
            self.gcode.append("G1 X0")
            self.gcode.append("G1 Y0")
        # closing section
        self.post_amble()
        return True

    def calculate_points(self):
        left = []
        right = []
        top = []
        bottom = []
        step = self.stepover * 1.4142
        # calculate the points on the 4 sides
        y = step
        while y <= self.size_y:
            left.append(QPointF(0.0, y))
            y += step
        x = y - self.size_y
        while x <= self.size_x:
            top.append(QPointF(x, self.size_y))
            x += step
        x = step
        while x <= self.size_x:
            bottom.append(QPointF(x, 0.0))
            x += step
        y = x - self.size_x
        while y <= self.size_y:
            right.append(QPointF(self.size_x, y))
            y += step
        start = left + top
        end = bottom + right
        return (start, end)

    def raster_0(self):
        i = 1
        x = (0.0, self.size_x)
        next_x = self.size_x
        next_y = 0.0
        self.gcode.append(f"G1 X{next_x} F{self.xy_feedrate}")
        while next_y < self.size_y:
            i ^= 1
            next_y = min(next_y + self.stepover, self.size_y)
            next_x = x[i]
            self.gcode.append(f"Y{next_y}")
            self.gcode.append(f"X{next_x}")

    def raster_45(self):
        start, end = self.calculate_points()
        step = self.stepover * 1.4142
        self.gcode.append(f"G1 Y{start[0].y()} F{self.xy_feedrate}")
        # calculate toolpath
        i = 0
        while 1:
            x = end[i].x()
            y = end[i].y()
            self.gcode.append(f"G1 X{x:.3f} Y{y:.3f}")
            if y == 0.0: # bottom edge
                if x + step > self.size_x:
                    self.gcode.append(f"G1 X{self.size_x:.3f}")
            elif x == self.size_x: # right edge
                if y + step > self.size_y:
                    self.gcode.append(f"G1 X{self.size_x:.3f} Y{self.size_y:.3f}")
                    break
            else:
                self.parent.add_status('Error computing toolpath preview', ERROR)
                return
            i += 1
            if i == len(start): break
            self.gcode.append(f"G1 X{end[i].x():.3f} Y{end[i].y():.3f}")
            x = start[i].x()
            y = start[i].y()
            self.gcode.append(f"G1 X{x:.3f} Y{y:.3f}")
            if x == 0.0: # left edge
                if y + step > self.size_y:
                    self.gcode.append(f"G1 Y{self.size_y:.3f}")
            elif y == self.size_y: # top edge
                if x + step > self.size_x:
                    self.gcode.append(f"G1 X{self.size_x:.3f} Y{self.size_y:.3f}")
                    break
            else:
                self.parent.add_status('Error computing toolpath preview', ERROR)
                return
            i += 1
            if i == len(start): break
            self.gcode.append(f"G1 X{start[i].x():.3f} Y{start[i].y():.3f}")

    def raster_90(self):
        i = 1
        y = (0.0, self.size_y)
        next_x = 0.0
        next_y = self.size_y
        self.gcode.append(f"G1 Y{next_y} F{self.xy_feedrate}")
        while next_x < self.size_x:
            i ^= 1
            next_y = y[i]
            next_x = min(next_x + self.stepover, self.size_x)
            self.gcode.append(f"X{next_x}")
            self.gcode.append(f"Y{next_y}")

    def update_preview(self):
        if not self.validate(): return
        if self.rbtn_raster_0.isChecked():
            self.calculate_path = self.path_0
        elif self.rbtn_raster_45.isChecked():
            self.calculate_path = self.path_45
        elif self.rbtn_raster_90.isChecked():
            self.calculate_path = self.path_90
        self.scene.clear()
        self.calculate_path()
        margin = 20
        self.scene.setSceneRect(-margin, -margin, self.size_x + 2 * margin, self.size_y + 2 * margin)
        self.facing_preview.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
        self.scene.addPath(self.path, self.pen)
        self.scene.addRect(-4.0, -4.0, 8.0, 8.0, QPen(Qt.green), QBrush(Qt.green))
        end_point = self.path.currentPosition()
        self.scene.addRect(end_point.x() - 4.0, end_point.y() - 4.0, 8.0, 8.0, QPen(Qt.red), QBrush(Qt.red))

    def path_0(self):
        i = 1
        x = (0.0, self.size_x)
        y = 0.0
        self.path.clear()
        self.path.moveTo(0.0, 0.0)
        self.path.lineTo(x[i], 0.0)
        while y < self.size_y:
            y = min(y + self.stepover, self.size_y)
            self.path.lineTo(x[i], y)
            i ^= 1
            self.path.lineTo(x[i], y)

    def path_45(self):
        start, end = self.calculate_points()
        step = self.stepover * 1.4142
        self.path.clear()
        self.path.moveTo(0.0, 0.0)
        # calculate toolpath
        i = 0
        self.path.lineTo(start[0])
        while 1:
            self.path.lineTo(end[i])
            x = self.path.currentPosition().x()
            y = self.path.currentPosition().y()
            if y == 0.0: # bottom edge
                if x + step > self.size_x:
                    self.path.lineTo(self.size_x, 0.0)
            elif x == self.size_x: # right edge
                if y + step > self.size_y:
                    self.path.lineTo(self.size_x, self.size_y)
                    break
            else:
                self.parent.add_status('Error computing toolpath preview', ERROR)
                return
            i += 1
            if i == len(start): break
            self.path.lineTo(end[i])
            self.path.lineTo(start[i])
            x = self.path.currentPosition().x()
            y = self.path.currentPosition().y()
            if x == 0.0: # left edge
                if y + step > self.size_y:
                    self.path.lineTo(0.0, self.size_y)
            elif y == self.size_y: # top edge
                if x + step > self.size_x:
                    self.path.lineTo(self.size_x, self.size_y)
                    break
            else:
                self.parent.add_status('Error computing toolpath preview', ERROR)
                return
            i += 1
            if i == len(start): break
            self.path.lineTo(start[i])

    def path_90(self):
        i = 1
        x = 0.0
        y = (0.0, self.size_y)
        self.path.clear()
        self.path.moveTo(0.0, 0.0)
        self.path.lineTo(0.0, y[i])
        while x < self.size_x:
            x = min(x + self.stepover, self.size_x)
            self.path.lineTo(x, y[i])
            i ^= 1
            self.path.lineTo(x, y[i])

    # required code for subscriptable objects
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)
