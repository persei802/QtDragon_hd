#!/usr/bin/env python3
# Event filter to allow lineEdit objects to be input with a calculator widget
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

import sys
import os
from PyQt5.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt5 import QtGui, QtWidgets
from qtvcp.core import Info
from qtvcp.widgets.calculator import Calculator

INFO = Info()


class EventFilter(QObject):
    def __init__(self, widgets):
        super().__init__()
        self.w = widgets
        self.use_calc = False
        self.line_list = []
        self._nextIndex = 0
        self.hilightStyle = "border: 1px solid cyan;"
        self._oldStyle = ''
        self.accept_only = False
        self.calc = CalcInput()

        self.tmpl = '.3f' if INFO.MACHINE_IS_METRIC else '.4f'

        self.calc.apply_action.connect(lambda: self.calc_data(apply=True))
        self.calc.next_action.connect(lambda: self.calc_data(next=True))
        self.calc.back_action.connect(lambda: self.calc_data(back=True))
        self.calc.accepted.connect(lambda: self.calc_data(accept=True))
        self.calc.rejected.connect(self.calc_data)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.FocusIn:
            if isinstance(obj, QtWidgets.QLineEdit) and self.use_calc:
                # only if mouse selected
                if event.reason() == 0:
                    self._nextIndex = self.line_list.index(obj.objectName().replace('lineEdit_',''))
                    self.popEntry(obj)
                    obj.clearFocus()
                    event.accept()
                    return True
        return False

    def popEntry(self, obj, next=False):
        obj.setStyleSheet(self.hilightStyle)
        self.calc.setWindowTitle(f"Enter data for {obj.objectName().replace('lineEdit_','')}")
        preset = obj.text()
        if preset == '': preset = '0'
        self.calc.display.setText(preset)
        if not next:
            self.calc.show()

    def calc_data(self, next=False, back=False, apply=False, accept=False):
        line = self.line_list[self._nextIndex]
        self.w[f'lineEdit_{line}'].setStyleSheet(self._oldStyle)
        if self.accept_only:
            if accept:
                text = self.calc.display.text()
                value = float(text)
                validator = self.check_validator(self.w[f'lineEdit_{line}'])
                if validator == 'int':
                    value = int(value)
                    self.w[f'lineEdit_{line}'].setText(str(value))
                elif validator == 'float':
                    self.w[f'lineEdit_{line}'].setText(f'{value:{self.tmpl}}')
            return
        if next:
            self._nextIndex += 1
            if self._nextIndex == len(self.line_list):
                self._nextIndex = 0
        elif back:
            self._nextIndex -= 1
            if self._nextIndex < 0:
                self._nextIndex = len(self.line_list) - 1
        elif apply or accept:
            text = self.calc.display.text()
            value = float(text)
            validator = self.check_validator(self.w[f'lineEdit_{line}'])
            if validator == 'int':
                value = int(value)
                self.w[f'lineEdit_{line}'].setText(str(value))
            elif validator == 'float':
                self.w[f'lineEdit_{line}'].setText(f'{value:{self.tmpl}}')
            if apply:
                self._nextIndex += 1
                if self._nextIndex == len(self.line_list):
                    self._nextIndex = 0
        if next or back or apply:
            newobj = self.w[f'lineEdit_{self.line_list[self._nextIndex]}']
            self.popEntry(newobj, True)

    def check_validator(self, obj):
        validator = obj.validator()
        if isinstance(validator, QtGui.QIntValidator): return 'int'
        if isinstance(validator, QtGui.QDoubleValidator): return 'float'
        if isinstance(validator, QtGui.QRegExpValidator):
            pattern = validator.regExp().pattern()
            if pattern ==  r'^\d{0,5}$': return 'int'
            if pattern ==  r'^((\d{1,3}(\.\d{1,4})?)|(\.\d{1,4}))$': return 'float'
            if pattern ==  r'^((\d{1,4}(\.\d{1,3})?)|(\.\d{1,3}))$': return 'float'
        return None

    def set_calc_mode(self, mode):
        self.use_calc = mode

    def set_line_list(self, data):
        self.line_list = data

    def set_old_style(self, style):
        self._oldStyle = style

    def set_accept_mode(self, mode):
        self.accept_only = mode

    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)

# sub-classed Calculator so button actions can be redefined
class CalcInput(Calculator):
    apply_action = pyqtSignal()
    next_action = pyqtSignal()
    back_action = pyqtSignal()

    def __init__(self):
        super(CalcInput, self).__init__()
        
    def applyAction(self):
        self.apply_action.emit()

    def nextAction(self):
        self.next_action.emit()

    def backAction(self):
        self.back_action.emit()


