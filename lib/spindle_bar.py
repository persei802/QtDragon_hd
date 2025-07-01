#!/usr/bin/env python3
#
# Copyright (c) 2025  Jim Sloot <persei802@gmail.com>
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
#
# used to capture left click events for spindle power bar

from PyQt5.QtWidgets import QProgressBar, QMenu, QAction
from PyQt5.QtCore import Qt, QPoint, pyqtSignal

class SpindleBar(QProgressBar):
    role_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
         
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.show_menu()
        else:
            super().mousePressEvent(event)
            
    def show_menu(self):
        top_left = self.mapToGlobal(self.rect().topLeft())
        bottom_left = top_left + QPoint(0, self.height())
        menu = QMenu(self)
        action_power = QAction("Power", self)
        action_voltage= QAction("Voltage", self)
        action_current = QAction("Current", self)
        
        menu.addAction(action_power)
        menu.addAction(action_voltage)
        menu.addAction(action_current)

        action_power.triggered.connect(lambda: self.role_changed.emit('power'))
        action_voltage.triggered.connect(lambda: self.role_changed.emit('volts'))
        action_current.triggered.connect(lambda: self.role_changed.emit('amps'))
        
        menu.exec_(bottom_left)
