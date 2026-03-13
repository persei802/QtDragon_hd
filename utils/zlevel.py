#!/usr/bin/env python3
# Copyright (c) 2026 Jim Sloot (persei802@gmail.com)
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
import mmap
import re
import math
import hal
import struct
import numpy as np
import matplotlib as mpl

from lib.event_filter import EventFilter
from utils.utils_mixin import Common

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQt5 import uic
from PyQt5.QtGui import QIntValidator, QDoubleValidator
from PyQt5.QtWidgets import QWidget, QApplication

from qtvcp.core import Status, Action, Info, Path, Qhal

INFO = Info()
STATUS = Status()
ACTION = Action()
PATH = Path()
QHAL = Qhal()
HERE = os.path.dirname(os.path.abspath(__file__))
HELP = os.path.join(PATH.CONFIGPATH, "help_files")
WARNING = 1
ERROR = 2
SHM_PATH = '/dev/shm/linuxcnc_surface_map'
MAX_NX = 200
MAX_NY = 200
HEADER_SIZE = 44
GRID_SIZE = MAX_NX * MAX_NY * 8
TOTAL_SIZE = HEADER_SIZE + GRID_SIZE


class SurfaceMap(FigureCanvas):
    def __init__(self, parent=None):
        self.figure = Figure()
        super().__init__(self.figure)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setFocusPolicy(False)
        self.ax3d = self.figure.add_subplot(111, projection='3d')
        self.ax3d.mouse_init = lambda *args, **kwargs: None
        self.ax3d.set_navigate(False)

    def plot(self, data):
        X, Y, Z = data
        self.ax3d.clear()
        self.ax3d.plot_surface(X, Y, Z, cmap='viridis')
        self.ax3d.set_xlabel('X Axis')
        self.ax3d.set_ylabel('Y Axis')
        self.ax3d.set_zlabel('Z Deviation')
        self.draw()

    def clear_plot(self):
        self.ax3d.clear()
        self.draw()

class HeatMap(FigureCanvas):
    def __init__(self, parent=None):
        self.figure = Figure()
        super().__init__(self.figure)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setFocusPolicy(False)
        self.ax2d = self.figure.add_subplot(111)
        self.ax2d.set_navigate(False)
        self.cbar = None

    def plot(self, data):
        X, Y, Z = data
        self.ax2d.clear()
        if self.cbar:
            self.cbar.remove()
        c = self.ax2d.contourf(X, Y, Z, 50)
        self.cbar = self.figure.colorbar(c, ax=self.ax2d)
        self.ax2d.set_xlabel("X Axis")
        self.ax2d.set_ylabel("Y Axis")
        self.draw()

    def clear_plot(self):
        self.ax2d.clear()
        if self.cbar:
            self.cbar.remove()
            self.cbar = None
        self.draw()

class ContourMap(FigureCanvas):
    def __init__(self, parent=None):
        self.figure = Figure()
        super().__init__(self.figure)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setFocusPolicy(False)
        self.ax2d = self.figure.add_subplot(111)
        self.ax2d.set_navigate(False)

    def plot(self, data):
        X, Y, Z = data
        self.ax2d.clear()
        levels = np.arange(np.min(Z), np.max(Z), 0.5)
        self.contours = self.ax2d.contour(X, Y, Z, levels=8, colors='white')
        self.ax2d.clabel(self.contours, inline=True, fontsize=8)
        self.draw()

    def clear_plot(self):
        self.ax2d.clear()
        self.draw()


class ZLevel(QWidget, Common):
    def __init__(self, parent=None):
        super(ZLevel, self).__init__()
        self.parent = parent         # reference to setup_utils
        self.h = self.parent.parent  # reference to handler file
        self.shm = None
        self.user_path = os.path.expanduser('~/linuxcnc/nc_files')
        self.helpfile = 'zlevel_help.html'
        self.dialog_code = 'CALCULATOR'
        self.kbd_code = 'KEYBOARD'
        self.tool_code= 'TOOLCHOOSER'
        self.default_style = ''
        self.geometry = None
        self.tmpl = '.3f' if INFO.MACHINE_IS_METRIC else '.4f'
        # Load the widgets UI file:
        self.filename = os.path.join(HERE, 'zlevel.ui')
        try:
            self.instance = uic.loadUi(self.filename, self)
        except AttributeError as e:
            print("Error: ", e)

        # Initial values
        self.probe_results = None
        self.help_text = []

        self.int_inputs = ['size_x', 'size_y', 'steps_x', 'steps_y', 'probe_tool', 'probe_vel']
        self.float_inputs = ['z_safe', 'max_probe', 'start_height']
        # quickest way to initialize variables
        self.set_unit_labels()
        self.validate()
        # list of zero reference locations
        self.reference = ["top-left", "top-right", "center", "bottom-left", "bottom-right"]
        # set validators for lineEdits
        self.lineEdit_size_x.setValidator(QIntValidator(0, 9999))
        self.lineEdit_size_y.setValidator(QIntValidator(0, 9999))
        self.lineEdit_steps_x.setValidator(QIntValidator(0, 100))
        self.lineEdit_steps_y.setValidator(QIntValidator(0, 100))
        self.lineEdit_probe_tool.setValidator(QIntValidator(1, 100))
        self.lineEdit_probe_vel.setValidator(QIntValidator(0, 9999))
        self.lineEdit_z_safe.setValidator(QDoubleValidator(0, 999, 3))
        self.lineEdit_max_probe.setValidator(QDoubleValidator(0, 999, 3))
        self.lineEdit_start_height.setValidator(QDoubleValidator(0, 999, 3))
        
        # setup event filter to catch focus_in events
        self.event_filter = EventFilter(self)
        parm_list = []
        for line in self.int_inputs:
            self[f'lineEdit_{line}'].installEventFilter(self.event_filter)
            parm_list.append(line)
        for line in self.float_inputs:
            self[f'lineEdit_{line}'].installEventFilter(self.event_filter)
            parm_list.append(line)
        self.lineEdit_gcode_program.installEventFilter(self.event_filter)
        self.lineEdit_comment.installEventFilter(self.event_filter)
        self.event_filter.set_line_list(parm_list)
        self.event_filter.set_kbd_list(['gcode_program', 'comment'])
        self.event_filter.set_tool_list('probe_tool')
        self.event_filter.set_parms(('_zlevel_', True))

        # populate combobox
        self.cmb_zero_ref.addItems(self.reference)
        self.cmb_zero_ref.setCurrentIndex(2)

        # signal connections
        self.chk_use_calc.stateChanged.connect(lambda state: self.event_filter.set_dialog_mode(state))
        self.rbtn_steps.clicked.connect(lambda state: self.steps_changed(state))
        self.rbtn_offset.clicked.connect(lambda state: self.steps_changed(state))
        self.btn_save_gcode.pressed.connect(self.save_gcode)
        self.btn_help.pressed.connect(self.show_help)
        # setup compensation map objects
        mpl.rcParams.update({'text.color': '#f0f0f0', 'axes.labelcolor': '#f0f0f0', 'axes.edgecolor': '#f0f0f0'})
        mpl.rcParams.update({'xtick.color': '#f0f0f0', 'ytick.color': '#f0f0f0'})
        mpl.rcParams.update({'axes.facecolor': '#303030', 'figure.facecolor': '#303030'})
        self.canvas1 = SurfaceMap()
        self.canvas2 = HeatMap()
        self.canvas3 = ContourMap()
        self.layout_surface.addWidget(self.canvas1)
        self.layout_heatmap.addWidget(self.canvas2)
        self.layout_contour.addWidget(self.canvas3)

    def _hal_init(self):
        def homed_on_status():
            return (STATUS.machine_is_on() and (STATUS.is_all_homed() or INFO.NO_HOME_REQUIRED))
        STATUS.connect('general', self.dialog_return)
        STATUS.connect('state_off', lambda w: self.setEnabled(False))
        STATUS.connect('state_estop', lambda w: self.setEnabled(False))
        STATUS.connect('interp-idle', lambda w: self.setEnabled(homed_on_status()))
        STATUS.connect('all-homed', lambda w: self.setEnabled(True))
        STATUS.connect('file-loaded', lambda w, fname: self.program_loaded(fname))

        self.default_style = self.lineEdit_size_x.styleSheet()
        QHAL.comp.setprefix('zlevel')
        self.comp_enable = QHAL.newpin("enable", hal.HAL_BIT, hal.HAL_OUT)
        self.comp_enable.set(False)

        # create shared memory structure
        self.shm = self.create_or_open_shm()

    def closing_cleanup__(self):
        try:
            os.remove(SHM_PATH)
        except FileNotFoundError:
            pass

## Calls from STATUS
    def dialog_return(self, w, message):
        rtn = message['RETURN']
        name = message.get('NAME')
        obj = message.get('OBJECT')
        code = bool(message.get('ID') == '_zlevel_')
        next = message.get('NEXT', False)
        back = message.get('BACK', False)
        if code and name == self.dialog_code:
            obj.setStyleSheet(self.default_style)
            if rtn is not None:
                if obj.objectName().replace('lineEdit_', '') in ['probe_tool', 'size_x', 'size_y']:
                    obj.setText(str(int(rtn)))
                elif obj.objectName().replace('lineEdit_', '') in ['steps_x', 'steps_y']:
                    if obj.validator() == QIntValidator:
                        obj.setText(str(int(rtn)))
                    else:
                        obj.setText(f'{rtn:{self.tmpl}}')
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

    def program_loaded(self, fname):
        self.probe_results = None
        self.canvas1.clear_plot()
        self.canvas2.clear_plot()
        self.canvas3.clear_plot()
        path = os.path.dirname(fname)
        base = os.path.basename(fname)
        if base.startswith('probe_'):
            probe_results = os.path.join(path, base.replace('ngc', 'txt'))
        else:
            probe_results = os.path.join(path, f"probe_{base.replace('ngc', 'txt')}")
        self.lineEdit_gcode_program.setText(fname)
        if os.path.isfile(probe_results):
            self.lbl_probe_data.setText(f'Probe result data found in {probe_results}')
            self.probe_results = probe_results
            # create probe points file and plot maps
            points = self.load_probe_file(probe_results)
            plane = self.fit_plane(points)
            comp_map = self.generate_map(points, plane)
            grid = self.build_grid(comp_map)
            if points is not None:
                self.write_shared_memory(grid)
                data = self.get_plot_data(comp_map)
                self.canvas1.plot(data)
                self.canvas2.plot(data)
                self.canvas3.plot(data)
        else:
            self.lbl_probe_data.setText('No probe result file found')

## Calls from widgets
    def save_gcode(self):
        if not self.validate(): return
        if not self.calculate_steps(): return
        pre = self.lineEdit_gcode_program.text()
        caption = 'Save Probe Program'
        _dir = os.path.expanduser('~/linuxcnc/nc_files')
        _dir = f'{_dir}/{pre}'
        _filter = "ngc Files (*.ngc)"
        fname, _ = self.save_program_file(self, caption, _dir, _filter)
        if fname:
            path = os.path.dirname(fname)
            program = os.path.basename(fname)
            if not program.startswith('probe_'):
                program = 'probe_' + program
            base, ext = os.path.splitext(program)
            if ext != '.ngc':
                program = base + '.ngc'
            probe = program.replace('ngc', 'txt')
            probe_name = os.path.join(path, probe)
            saveFile = os.path.join(path, program)
            self.calculate_gcode(saveFile, probe_name)
            ACTION.OPEN_PROGRAM(saveFile)
            self.h.add_status(f'Saved probe program to {saveFile}')
        else:
            self.h.add_status('Probe program save cancelled')

    def steps_changed(self, state):
        if state and self.sender() == self.rbtn_offset:
            self.lineEdit_steps_x.setValidator(QDoubleValidator(0, 999, 3))
            self.lineEdit_steps_y.setValidator(QDoubleValidator(0, 999, 3))
        elif state and self.sender() == self.rbtn_steps:
            self.lineEdit_steps_x.setValidator(QIntValidator(2, 999))
            self.lineEdit_steps_y.setValidator(QIntValidator(2, 999))

    def calculate_steps(self):
        self.size_x = int(self.lineEdit_size_x.text())
        self.size_y = int(self.lineEdit_size_y.text())
        if self.rbtn_offset.isChecked():
            # steps based on offset
            self.x_inc = float(self.lineEdit_steps_x.text())
            self.y_inc = float(self.lineEdit_steps_y.text())
            try:
                self.steps_x = int(self.size_x / self.x_inc) + 1
                self.steps_y = int(self.size_y / self.y_inc) + 1
            except ZeroDivisionError as e:
                self.h.add_status(e, ERROR)
                return False
        else:
            # steps based on number
            self.steps_x = int(self.lineEdit_steps_x.text())
            self.steps_y = int(self.lineEdit_steps_y.text())
            try:
                self.x_inc = self.size_x / (self.steps_x - 1)
                self.y_inc = self.size_y / (self.steps_y - 1)
            except ZeroDivisionError as e:
                self.h.add_status(e, ERROR)
                return False
        return True

    def show_help(self):
        fname = os.path.join(HELP, self.helpfile)
        self.parent.show_help_page(fname)

## Helper functions
    def create_or_open_shm(self):
        fd = os.open(SHM_PATH, os.O_CREAT | os.O_RDWR)
        os.ftruncate(fd, TOTAL_SIZE)
        shm = mmap.mmap(fd, TOTAL_SIZE, mmap.MAP_SHARED, mmap.PROT_WRITE | mmap.PROT_READ)
        os.close(fd)
        return shm

    def load_probe_file(self, fname):
        try:
            data = np.loadtxt(fname, dtype = float, delimiter = " ", usecols = (0, 1, 2))
        except Error as e:
            self.h.add_status(f'Unable to read surface map data', ERROR)
            return None
        return data

    def get_plot_data(self, map_data):
        pts = []
        for parts in map_data:
            x = float(parts[0])
            y = float(parts[1])
            z = float(parts[2])
            pts.append((x, y, z))
        data = np.array(pts)
        x = np.round(data[:, 0], 1)
        y = np.round(data[:, 1], 1)
        z = np.round(data[:, 2], 3)
        x_unique = np.unique(x)
        y_unique = np.unique(y)
        X,Y = np.meshgrid(x_unique, y_unique)
        Z = z.reshape(len(y_unique), len(x_unique))
        return (X, Y, Z)

    def fit_plane(self, points):
        X = points[:,0]
        Y = points[:,1]
        Z = points[:,2]
        A = np.c_[X, Y, np.ones(len(X))]
        C, _, _, _ = np.linalg.lstsq(A, Z, rcond=None)
        a, b, c = C
        return a, b, c
    
    def generate_map(self, points, plane):
        a, b, c = plane
        result = []
        for x, y, z in points:
            plane_z = a*x + b*y + c
            deviation = z - plane_z
            result.append((x, y, deviation))
        return result

    def build_grid(self, points):
        pts = np.array(points)
        xs = np.unique(pts[:,0])
        ys = np.unique(pts[:,1])
        nx = len(xs)
        ny = len(ys)
        zgrid = np.zeros((nx, ny))
        x_index = {x:i for i,x in enumerate(xs)}
        y_index = {y:i for i,y in enumerate(ys)}
        for x,y,z in pts:
            ix = x_index[x]
            iy = y_index[y]
            zgrid[ix,iy] = z
        xmin = xs.min()
        xmax = xs.max()
        ymin = ys.min()
        ymax = ys.max()
        return {
            "nx": nx,
            "ny": ny,
            "xmin": xmin,
            "xmax": xmax,
            "ymin": ymin,
            "ymax": ymax,
            "zgrid": zgrid}

    def write_shared_memory(self, grid):
        nx = grid["nx"]
        ny = grid["ny"]
        xmin = grid["xmin"]
        xmax = grid["xmax"]
        ymin = grid["ymin"]
        ymax = grid["ymax"]
        zgrid = grid["zgrid"]

        version = struct.unpack_from("I", self.shm, 0)[0]
        version = (version + 1) | 1
        struct.pack_into("I", self.shm, 0, version)
        struct.pack_into("I", self.shm, 4, nx)
        struct.pack_into("I", self.shm, 8, ny)
        struct.pack_into("d", self.shm, 12, xmin)
        struct.pack_into("d", self.shm, 20, xmax)
        struct.pack_into("d", self.shm, 28, ymin)
        struct.pack_into("d", self.shm, 36, ymax)
        z_bytes = np.zeros(MAX_NX*MAX_NY, dtype=np.float64)
        z_bytes[:nx*ny] = zgrid.ravel()
        self.shm[HEADER_SIZE:HEADER_SIZE + (MAX_NX * MAX_NY * 8)] = z_bytes.tobytes()
        struct.pack_into("I", self.shm, 0, version + 1)

    def calculate_gcode(self, fname, pname):
        # get start point
        zref = self.cmb_zero_ref.currentIndex()
        if zref == 2:
            x_start = -self.size_x / 2
            y_start = -self.size_y / 2
        else:
            x_start = 0 if zref == 0 or zref == 3 else -self.size_x
            y_start = 0 if zref == 3 or zref == 4 else -self.size_y
        # opening preamble
        self.line_num = 5
        self.file = open(fname, 'w')
        self.file.write("%\n")
        self.file.write(f"({self.lineEdit_comment.text()})\n")
        self.file.write(f"(Area: X {self.size_x} by Y {self.size_y})\n")
        self.file.write(f"(Steps: X {self.steps_x} by Y {self.steps_y})\n")
        self.file.write(f"(Safe Z travel height {self.z_safe})\n")
        self.file.write(f"(XY Zero point is {self.reference[zref]})\n")
        self.next_line("G17 G40 G49 G64 G90 P0.03")
        self.next_line("G92.1")
        self.next_line(f"M6 T{self.probe_tool}")
        self.next_line(f"G0 Z{self.z_safe}")
        # main section
        self.next_line(f"(PROBEOPEN {pname})")
        self.next_line("#100 = 0")
        self.next_line(f"O100 while [#100 LE {self.steps_y - 1}]")
        self.next_line(f"  G0 Y[{y_start} + {self.y_inc:.3f} * #100]")
        self.next_line("  #200 = 0")
        self.next_line(f"  O200 while [#200 LE {self.steps_x - 1}]")
        self.next_line(f"    G0 X[{x_start} + {self.x_inc:.3f} * #200]")
        self.next_line(f"    G0 Z{self.start_height}")
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
        if not self.check_int_blanks(self.int_inputs): return False
        if not self.check_float_blanks(self.float_inputs): return False
        for val in self.int_inputs:
            if self[val] <= 0:
                self[f'lineEdit_{val}'].setStyleSheet(self.red_border)
                self.h.add_status(f'{val} must be > 0', WARNING)
                return False
        for val in self.float_inputs:
            if self[val] <= 0.0:
                self[f'lineEdit_{val}'].setStyleSheet(self.red_border)
                self.h.add_status(f'{val} must be > 0.0', WARNING)
                return False
        if self.steps_x < 2 or self.steps_x > MAX_NX:
            self.lineEdit_steps_x.setStyleSheet(self.red_border)
            self.h.add_status(f"Steps X must be between 2 and {MAX_NX}", WARNING)
            return False
        if self.steps_y < 2 or self.steps_y > MAX_NY:
            self.lineEdit_steps_y.setStyleSheet(self.red_border)
            self.h.add_status(f"Steps Y must be between 2 and {MAX_NY}", WARNING)
            return False
        self.lineEdit_gcode_program.setStyleSheet(self.default_style)
        if not self.lineEdit_gcode_program.text():
            self.lineEdit_gcode_program.setStyleSheet(self.red_border)
            return False
        return True

    def next_line(self, text):
        self.file.write(f"N{self.line_num} " + text + "\n")
        self.line_num += 5

    def set_unit_labels(self):
        unit = "MM" if INFO.MACHINE_IS_METRIC else "IN"
        self.lbl_probe_area_unit.setText(unit)
        self.lbl_probe_vel_unit.setText(f'{unit}/MIN')
        self.lbl_z_safe_unit.setText(unit)
        self.lbl_start_height_unit.setText(unit)
        self.lbl_max_probe_unit.setText(unit)

## Calls from handler
    def get_map(self, state):
        if state and self.probe_results is not None:
            self.comp_enable.set(True)
        elif not state:
            self.comp_enable.set(False)
        return self.probe_results

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

