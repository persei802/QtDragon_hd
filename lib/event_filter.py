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
# used to capture focus_in events for lineEdit widgets

import sys
import os
from PyQt5.QtCore import QEvent, QObject, Qt
from PyQt5 import QtWidgets
from qtvcp.core import Action
from qtvcp import logger

LOG = logger.getLogger(__name__)
LOG.setLevel(logger.INFO) # One of DEBUG, INFO, WARNING, ERROR, CRITICAL
ACTION = Action()

class EventFilter(QObject):
    def __init__(self, parent=None):
        super().__init__()
        self.parent = parent
        self.use_dialog = False
        self.id = ''
        self.cycle = False
        self.hilightStyle = "border: 1px solid cyan;"
        self._nextIndex = 0
        self.line_list = []
        self.kbd_list = []
        self.tool_list = []

    def eventFilter(self, obj, event):
        if event.type() == QEvent.FocusIn:
            if isinstance(obj, QtWidgets.QLineEdit) and self.use_dialog:
                # only if mouse selected
                if event.reason () == 0:
                    if obj.objectName().replace('lineEdit_','') in self.kbd_list:
                        self.show_kbd(obj)
                    elif obj.objectName().replace('lineEdit_','') in self.tool_list:
                        self.show_tool_chooser(obj)
                    else:
                        self._nextIndex = self.line_list.index(obj.objectName().replace('lineEdit_',''))
                        self.show_calc(obj)
                    obj.clearFocus()
                    event.accept()
                    return True
        return False

    def show_calc(self, obj, next=False):
        obj.setStyleSheet(self.hilightStyle)
        QtWidgets.qApp.processEvents()

        mess = {'NAME': 'CALCULATOR',
                'ID': self.id,
                'PRELOAD': obj.text(),
                'OBJECT': obj,
                'TITLE': f'{obj.toolTip().upper()}',
                'GEONAME': '__calculator',
                'OVERLAY': False,
                'NEXT': next,
                'WIDGETCYCLE': self.cycle}
        LOG.debug(f'message sent:{mess}')
        ACTION.CALL_DIALOG(mess)

    def show_kbd(self, obj):
        obj.setStyleSheet(self.hilightStyle)
        mess = {'NAME': 'KEYBOARD',
                'ID': self.id,
                'PRELOAD': obj.text(),
                'TITLE': 'Enter item text',
                'GEONAME': '__keyboard',
                'OBJECT': obj}
        LOG.debug(f'message sent:{mess}')
        ACTION.CALL_DIALOG(mess)

    def show_tool_chooser(self, obj):
        mess = {'NAME' : 'TOOLCHOOSER',
                'ID' : self.id,
                'GEONAME': '__toolchooser',
                'OBJECT': obj}
        LOG.debug(f'message sent:{mess}')
        ACTION.CALL_DIALOG(mess)

    def findNext(self):
        while 1:
            self._nextIndex += 1
            if self._nextIndex == len(self.line_list):
                self._nextIndex = 0
            newobj = self.parent[f'lineEdit_{self.line_list[self._nextIndex]}']
            if newobj.isVisible():
                break
        return newobj

    def findBack(self):
        while 1:
            self._nextIndex -= 1
            if self._nextIndex == -1:
                self._nextIndex = len(self.line_list) - 1
            newobj = self.parent[f'lineEdit_{self.line_list[self._nextIndex]}']
            if newobj.isVisible():
                break
        return newobj

    def set_dialog_mode(self, mode):
        self.use_dialog = mode

    def set_line_list(self, data):
        self.line_list = data

    def set_kbd_list(self, data):
        self.kbd_list = data

    def set_tool_list(self, data):
        self.tool_list = data

    def set_parms(self, parms):
        self.id, self.cycle = parms

    # required code for subscriptable objects
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)
