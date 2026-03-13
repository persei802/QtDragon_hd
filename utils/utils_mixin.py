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

import tempfile
import atexit

from qtvcp.core import Info
from PyQt5.QtWidgets import QFileDialog, QLineEdit

INFO = Info()

class Common():
    def __init__(self):
        self.min_rpm = INFO.get_safe_int("DISPLAY", "MIN_SPINDLE_0_SPEED")
        self.max_rpm = INFO.get_safe_int("DISPLAY", "MAX_SPINDLE_0_SPEED")
        self.max_feed = INFO.get_safe_int("DISPLAY", "MAX_LINEAR_VELOCITY") * 60
        self.red_border = "border: 2px solid red;"
        self.dialog_code = 'CALCULATOR'
        self.kbd_code = 'KEYBOARD'
        self.tool_code = 'TOOLCHOOSER'

    def post_amble(self):
        self.next_line("G90")
        self.next_line(f"G0 Z{self.safe_z}")
        self.next_line("M9")
        self.next_line("M5")
        self.next_line("M2")
        self.gcode.append("%")

    def check_float_blanks(self, items):
        for name in items:
            widget = self[f'lineEdit_{name}']
            text = widget.text().strip()
            if not text:
                widget.setStyleSheet(self.red_border)
                return False
            self[name] = float(text)
            widget.setStyleSheet(self.default_style)
        return True

    def check_int_blanks(self, items):
        for name in items:
            widget = self[f'lineEdit_{name}']
            text = widget.text().strip()
            if not text:
                widget.setStyleSheet(self.red_border)
                return False
            self[name] = int(text)
            widget.setStyleSheet(self.default_style)
        return True

    def save_program_file(self, parent, caption, directory, filter):
        dialog = QFileDialog(parent, caption, directory, filter)
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        dialog.setFileMode(QFileDialog.AnyFile)
        dialog.setDefaultSuffix("ngc")
        for le in dialog.findChildren(QLineEdit):
            le.setCompleter(None)
        if self.geometry:
            dialog.restoreGeometry(self.geometry)
        if dialog.exec():
            self.geometry = dialog.saveGeometry()
            files = dialog.selectedFiles()
            if files:
                return files[0], dialog.selectedNameFilter()
        return '', ''

    def make_temp(self, pname):
        fd, path = tempfile.mkstemp(prefix=pname, suffix='.ngc')
        atexit.register(lambda: os.remove(path))
        return path

