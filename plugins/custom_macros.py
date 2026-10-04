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


import sys
import os
from lib.event_filter import EventFilter
from qtpy import uic
from qtpy.QtCore import QSettings, Signal, Slot
from qtpy.QtWidgets import QWidget, QLabel
from qtvcp.core import Info, Status

INFO = Info()
STATUS = Status()
WARNING = 1
ERROR = 2
HERE = os.path.dirname(os.path.abspath(__file__))

PLUGIN_INFO = {
    'mod_name' : 'custom_macros',
    'class_name' : 'CustomMacros',
    'item_text' : 'CUSTOM MACROS',
    'version' : '2.0',
    'description' : '''Custom Macros
Create user defined macro buttons that can be modified at runtime
Macro buttons created in the INI file are not affected
Macro buttons are preserved between sessions
'''
}


class ClickableLabel(QLabel):
    label_clicked = Signal(int)
    def __init__(self, parent=None):
        super().__init__(parent)

    def mousePressEvent(self, event):
        self.label_clicked.emit(self.property('index'))
        super().mousePressEvent(event)

class CustomMacros(QWidget):
    def __init__(self, parent=None):
        super(CustomMacros, self).__init__()
        self.parent = parent #reference to setup_utils
        self.h = parent.parent # reference to handler
        self.w = parent.w # reference to handler widgets
        self.settings = QSettings(os.path.join(HERE, 'settings.ini'), QSettings.IniFormat)
        self.kbd_code = 'KEYBOARD'
        self.old_index = 0
        self.custom_macros = {}
        # Load the widgets UI file:
        self.filename = os.path.join(HERE, 'custom_macros.ui')
        try:
            self.instance = uic.loadUi(self.filename, self)
        except AttributeError as e:
            self.parent.add_status(e, WARNING)
        # install event filter to capture focus events for lineEdits
        self.event_filter = EventFilter(self)
        self.lineEdit_cmd1.installEventFilter(self.event_filter)
        self.lineEdit_cmd2.installEventFilter(self.event_filter)
        self.lineEdit_cmd3.installEventFilter(self.event_filter)
        self.lineEdit_text.installEventFilter(self.event_filter)
        self.event_filter.set_kbd_list(['cmd1', 'cmd2', 'cmd3', 'text'])
        self.event_filter.set_parms(('_macros_', True))
        self.prefill_labels()
        # mouse press events from clickable labels
        for i in range(20):
            self[f'lbl_macro{i}'].label_clicked.connect(lambda idx: self.label_pressed(idx))
        # signal connections
        self.btn_apply.pressed.connect(self.apply_command)
        self.btn_clear.pressed.connect(self.clear_lines)
        self.chk_use_keyboard.stateChanged.connect(lambda state: self.event_filter.set_dialog_mode(state))
        # connect all buttons to macro handler - it won't get called if the button is disabled
        for i in range(20):
            if i in self.h.macros_defined: continue
            self.w[f'btn_macro{i}'].pressed.connect(lambda i=i: self.h.macro_btn_pressed(i))
                
    def _hal_init(self):
        def homed_on_status():
            return (STATUS.machine_is_on() and (STATUS.is_all_homed() or INFO.NO_HOME_REQUIRED))
        STATUS.connect('interp-idle', lambda w: self.setEnabled(homed_on_status()))
        STATUS.connect('general', self.dialog_return)
        STATUS.connect('state_off', lambda w: self.setEnabled(False))
        STATUS.connect('all-homed', lambda w: self.setEnabled(True))
        self.default_style = self.lineEdit_cmd1.styleSheet()

    def closing_cleanup__(self):
        # save all custom macros to settings file
        for key, text in self.custom_macros.items():
            self.settings.setValue(f'macros/{key}', text)
        self.settings.sync()

    def prefill_labels(self):
        # prefill INI macro labels
        for i in self.h.macros_defined:
            self[f'lbl_macro{i}'].setText(self.w[f'btn_macro{i}'].text())
        # prefill custom macro labels
        self.settings.beginGroup('macros')
        keys = self.settings.allKeys()
        try:
            for key in keys:
                text = self.settings.value(key)
                self.custom_macros[int(key)] = text
                line = text.split(',')
                cmds = line[0]
                lbl = line[1].replace(r'\n', '\n')
                tip = cmds.replace(';','\n')
                tooltip = f'MDI CMD MACRO{key}:\n{tip}'
                self[f'lbl_macro{key}'].setText(lbl)
                self.w[f'btn_macro{key}'].setProperty('ini_mdi_cmd', cmds)
                self.w[f'btn_macro{key}'].setText(lbl)
                self.w[f'btn_macro{key}'].setToolTip(tooltip)
        except Exception as e:
            self.parent.add_status(f'Prefill error: {e}', ERROR)
        self.settings.endGroup()

    def dialog_return(self, w, message):
        rtn = message['RETURN']
        name = message.get('NAME')
        obj = message.get('OBJECT')
        code = bool(message.get('ID') == '_macros_')
        if code and name == self.kbd_code:
            obj.setStyleSheet(self.default_style)
            obj.clearFocus()
            if rtn is not None:
                obj.setText(rtn)

    def apply_command(self):
        i = self.old_index
        line = self.assemble_command()
        if line is None:
            if i in self.custom_macros:
                self.custom_macros.pop(i)
                self.settings.remove(f'macros/{i}')
            self.w[f'btn_macro{i}'].setText('')
            self.w[f'btn_macro{i}'].setToolTip('Not defined')
            self.w[f'btn_macro{i}'].setEnabled(False)
            self[f'lbl_macro{i}'].setText('')
        else:
            if self.lineEdit_text.text() == '':
                self.parent.add_status('Macro button text is blank', WARNING)
                return
            self.custom_macros[i] = line
            text = line.split(',')
            cmd = text[0]
            tip = cmd.replace(';','\n')
            lbl = text[1].replace(r'\n', '\n')
            tooltip = f'MDI CMD MACRO{i}:\n{tip}'
            self[f'lbl_macro{i}'].setText(lbl)
            self.w[f'btn_macro{i}'].setProperty('ini_mdi_cmd', cmd)
            self.w[f'btn_macro{i}'].setText(lbl)
            self.w[f'btn_macro{i}'].setToolTip(tooltip)
            self.w[f'btn_macro{i}'].setEnabled(True)
        self.check_empty_groups()

    def clear_lines(self):
        self.lineEdit_cmd1.clear()
        self.lineEdit_cmd2.clear()
        self.lineEdit_cmd3.clear()
        self.lineEdit_text.clear()

    def set_all_readonly(self, state):
        self.lineEdit_cmd1.setReadOnly(state)
        self.lineEdit_cmd2.setReadOnly(state)
        self.lineEdit_cmd3.setReadOnly(state)
        self.lineEdit_text.setReadOnly(state)

    def assemble_command(self):
        text = self.lineEdit_text.text()
        cmd1 = self.lineEdit_cmd1.text()
        if not cmd1: return None
        cmd2 = self.lineEdit_cmd2.text()
        if not cmd2:
            command = f'{cmd1},{text}'
            return command
        cmd3 = self.lineEdit_cmd3.text()
        if not cmd3:
            command = f'{cmd1};{cmd2},{text}'
            return command
        command = f'{cmd1};{cmd2};{cmd3},{text}'
        return command

    def label_pressed(self, idx):
        self[f'lbl_macro{self.old_index}'].setStyleSheet('')
        self.old_index = idx
        self.clear_lines()
        if idx in self.h.macros_defined:
            self.set_all_readonly(True)
            self[f'lbl_macro{idx}'].setStyleSheet("border: 1px solid red;")
            text = self.w[f'btn_macro{idx}'].property('ini_mdi_cmd')
            self.btn_apply.setEnabled(False)
            self.btn_clear.setEnabled(False)
        else:
            self.set_all_readonly(False)
            self[f'lbl_macro{idx}'].setStyleSheet("border: 1px solid cyan;")
            text = self.w[f'btn_macro{idx}'].property('ini_mdi_cmd')
            self.btn_apply.setEnabled(True)
            self.btn_clear.setEnabled(True)
        if text is not None:
            cmds = text.split(';')
            for i in range(len(cmds)):
                self[f'lineEdit_cmd{i+1}'].setText(cmds[i])
        self.lineEdit_text.setText(self.w[f'btn_macro{idx}'].text())

    def check_empty_groups(self):
        show = False
        for i in range(10):
            if self.w[f'btn_macro{i}'].text():
                show = True
                break
        self.w.group1_macro_buttons.setVisible(show)
        show = False
        for i in range(10, 20):
            if self.w[f'btn_macro{i}'].text():
                show = True
                break
        self.w.group2_macro_buttons.setVisible(show)
        if self.w.group1_macro_buttons.isHidden() and self.w.group2_macro_buttons.isHidden():
            self.w.btn_marker.hide()
        else:
            self.w.btn_marker.show()

    # required code for subscriptable objects
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)
