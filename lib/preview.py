#!/usr/bin/env python3
# Copyright (c) 2025 Jim Sloot (persei802@gmail.com)
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
import gcode
import shutil
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtGui import QPainter, QPen, QColor
from PyQt5.QtCore import Qt, QPointF, QLine
from PyQt5.QtWidgets import QWidget
from qtvcp.core import Info, Path
from .base_canon import BaseCanon
from .base_canon import StatCanon

INFO = Info()
PATH = Path()


class Viewer(StatCanon):
    def __init__(self):
        super(Viewer, self).__init__()
        BaseCanon.__init__(self)
        self.path_points = list()
        self.parameter_file = ''
    # canon override functions
    def add_path_point(self, line_type, start_point, end_point):
        self.path_points.append((line_type, start_point[:2], end_point[:2]))

    def rotate_and_translate(self, x, y, z, a, b, c, u, v, w):
        return x, y, z, a, b, c, u, v, w

    def get_path_points(self):
        return self.path_points


class Preview(QWidget):
    def __init__(self):
        super(Preview, self).__init__()
        self.path_points = []
        self.x_coords = []
        self.y_coords = []
        self.width = 10
        self.height = 10
        self.scale = 1
        self.cx = 0.0
        self.cy = 0.0
        self.offset = QPointF(0.0, 0.0)
        self.viewer = Viewer()
        self.config_dir = PATH.CONFIGPATH
        self.parameter_file = os.path.join(self.config_dir, 'linuxcnc.var')
        self.temp_parameter_file = os.path.join(self.parameter_file + '.temp')

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(200, 200, 200, 255))
        self.draw_path(event, painter)
        
    def draw_path(self, event, qp):
        qp.setPen(QPen(Qt.yellow, 1))
        qp.translate((self.width/2) - self.cx, (self.height/2) + self.cy)
        qp.scale(1, -1)
        for i in range(len(self.x_coords)-1):
            if self.x_coords[i] == self.x_coords[i+1] and self.y_coords[i] == self.y_coords[i+1]: continue
            start = QPointF(self.x_coords[i] * self.scale, self.y_coords[i] * self.scale)
            end = QPointF(self.x_coords[i+1] * self.scale, self.y_coords[i+1] * self.scale)
            qp.drawLine(start, end)
        qp.end()

    def set_path_points(self):
        self.path_points = []
        points = self.viewer.get_path_points()
        for line in points:
            self.path_points.append(line[1])
            self.path_points.append(line[2])
        self.set_scale()

    def set_scale(self):
        self.width = self.size().width()
        self.height = self.size().height()
        self.x_coords, self.y_coords = zip(*self.path_points)
        xmin, xmax = min(self.x_coords), max(self.x_coords)
        ymin, ymax = min(self.y_coords), max(self.y_coords)
        dist_x = xmax - xmin
        dist_y = ymax - ymin
        try:
            scale_w = self.width / dist_x
            scale_h = self.height / dist_y 
            self.scale = min([scale_w, scale_h])
            self.scale = int(self.scale)
            self.cx = ((xmax + xmin)/2) * self.scale
            self.cy = ((ymax + ymin)/2) * self.scale
        except ZeroDivisionError:
            print('Zero division error')
            self.scale = 1

    def load_program(self, filename):
        BaseCanon.__init__(self)
        self.viewer.path_points = list()
        if os.path.exists(self.parameter_file):
            shutil.copy(self.parameter_file, self.temp_parameter_file)
        self.viewer.parameter_file = self.temp_parameter_file
        unitcode = "G21" if INFO.MACHINE_IS_METRIC else "G20"
        initcode = INFO.get_error_safe_setting("RS274NGC", "RS274NGC_STARTUP_CODE", "")
        load_result = True
        try:
            result, seq = gcode.parse(filename, self.viewer, unitcode, initcode)
            if result > gcode.MIN_ERROR:
                msg = gcode.strerror(result)
                fname = os.path.basename(filename)
                self.report_gcode_error(msg, seq, fname)
        except Exception as e:
            self.report_gcode_error(e)
            load_result = False
        finally:
            os.unlink(self.temp_parameter_file)
        return load_result

    def report_gcode_error(self, msg, seq=None, filename=None):
        if seq is None:
            print(f"GCode parse error: {msg}")
        else:
            print(f"GCode error in {filename} near line {seq}: {msg}")

