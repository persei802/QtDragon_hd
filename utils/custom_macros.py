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
from PyQt5 import uic
from PyQt5.QtWidgets import QWidget
from qtvcp.core import Info, Status

INFO = Info()
STATUS = Status()
WARNING = 1
HERE = os.path.dirname(os.path.abspath(__file__))

class CustomMacros(QWidget):
    def __init__(self, parent=None):
        super(CustomMacros, self).__init__()
        self.parent = parent #reference to setup_utils
        self.h = self.parent.parent # reference to handler
        self.w = self.parent.w # reference to handler widgets
        self.kbd_code = 'KEYBOARD'
        self.old_value = 0
        self.custom_macros = []
        # Load the widgets UI file:
        self.filename = os.path.join(HERE, 'custom_macros.ui')
        try:
            self.instance = uic.loadUi(self.filename, self)
        except AttributeError as e:
            self.h.add_status(e, WARNING)
        # install event filter to capture focus events for lineEdits
        self.event_filter = EventFilter(self)
        self.lineEdit_cmd1.installEventFilter(self.event_filter)
        self.lineEdit_cmd2.installEventFilter(self.event_filter)
        self.lineEdit_cmd3.installEventFilter(self.event_filter)
        self.lineEdit_text.installEventFilter(self.event_filter)
        self.event_filter.set_kbd_list(['cmd1', 'cmd2', 'cmd3', 'text'])
        self.event_filter.set_parms(('_macros_', True))
        self.prefill_labels()

    def _hal_init(self):
        def homed_on_status():
            return (STATUS.machine_is_on() and (STATUS.is_all_homed() or INFO.NO_HOME_REQUIRED))
        STATUS.connect('interp-idle', lambda w: self.setEnabled(homed_on_status()))
        STATUS.connect('general', self.dialog_return)
        STATUS.connect('state_off', lambda w: self.setEnabled(False))
        STATUS.connect('all-homed', lambda w: self.setEnabled(True))

        self.default_style = self.lineEdit_cmd1.styleSheet()
        self.btn_apply.pressed.connect(self.apply_command)
        self.btn_clear.pressed.connect(self.clear_lines)
        self.spinbox.valueChanged.connect(self.spin_value_changed)
        self.chk_use_keyboard.stateChanged.connect(lambda state: self.event_filter.set_dialog_mode(state))

        self.spinbox.setValue(0)
        self.spin_value_changed(0)

    def closing_cleanup__(self):
        # save all custom macros to qtdragon.pref file
        for key in self.custom_macros:
            self.spinbox.setValue(int(key))
            text = self.assemble_command()
            self.w.PREFS_.putpref(key, text, str, 'CUSTOM_MACROS')

    def prefill_labels(self):
        # prefill INI macro labels
        for i in self.h.macros_defined:
            self[f'lbl_macro{i}'].setText(self.w[f'btn_macro{i}'].text())
            cmds = self.w[f'btn_macro{i}'].get_command_text()
            for cmd in cmds:
                self[f'lbl_macro{i}'].setText(cmd)
        # prefill custom macro labels
        if self.w.PREFS_:
            macro_list = self.w.PREFS_.getall('CUSTOM_MACROS')
            for key in macro_list:
                self.custom_macros.append(key)
                text = macro_list[key]
                line = text.split(',')
                cmds = line[0]
                lbl = line[1].replace(r'\n', '\n')
                tip = cmds.replace(';','\n')
                tooltip = f'MDI CMD MACRO{key}:\n{tip}'
                self[f'lbl_macro{key}'].setText(lbl)
                self.w[f'btn_macro{key}'].set_mdi_command(True)
                self.w[f'btn_macro{key}'].set_command_text(cmds)
                self.w[f'btn_macro{key}'].setText(lbl)
                self.w[f'btn_macro{key}'].setToolTip(tooltip)

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
        i = self.spinbox.value()
        line = self.assemble_command()
        if line is None:
            self.w[f'btn_macro{i}'].set_mdi_command(False)
            self.w[f'btn_macro{i}'].set_command_text('')
            self.w[f'btn_macro{i}'].setText('')
            self.w[f'btn_macro{i}'].setToolTip('Not defined')
            self.w[f'btn_macro{i}'].setEnabled(False)
            self[f'lbl_macro{i}'].setText('')
            if self.w.PREFS_:
                self.w.PREFS_.removepref(str(i), 'CUSTOM_MACROS')
        else:
            text = line.split(',')
            cmd = text[0]
            tip = cmd.replace(';','\n')
            lbl = text[1].replace(r'\n', '\n')
            tooltip = f'MDI CMD MACRO{i}:\n{tip}'
            self[f'lbl_macro{i}'].setText(lbl)
            self.w[f'btn_macro{i}'].set_mdi_command(True)
            self.w[f'btn_macro{i}'].set_command_text(cmd)
            self.w[f'btn_macro{i}'].setText(lbl)
            self.w[f'btn_macro{i}'].setToolTip(tooltip)
        self.h.show_macros_clicked(self.w.btn_show_macros.isChecked())

    def clear_lines(self):
        self.lineEdit_cmd1.clear()
        self.lineEdit_cmd2.clear()
        self.lineEdit_cmd3.clear()
        self.lineEdit_text.clear()

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

    def spin_value_changed(self, idx):
        self[f'lbl_macro{self.old_value}'].setStyleSheet('')
        self.old_value = idx
        self.lineEdit_cmd1.clear()
        self.lineEdit_cmd2.clear()
        self.lineEdit_cmd3.clear()
        self.lineEdit_text.clear()
        if idx in self.h.macros_defined:
            self[f'lbl_macro{idx}'].setStyleSheet("border: 1px solid red;")
            key = self.w[f'btn_macro{idx}'].property('ini_mdi_key')
            text = INFO.get_ini_mdi_command(key)
            self.btn_apply.setEnabled(False)
        else:
            self[f'lbl_macro{idx}'].setStyleSheet("border: 1px solid cyan;")
            text = self.w[f'btn_macro{idx}'].get_command_text()
            self.btn_apply.setEnabled(True)
        cmds = text.split(';')
        for i in range(len(cmds)):
            self[f'lineEdit_cmd{i+1}'].setText(cmds[i])
        self.lineEdit_text.setText(self.w[f'btn_macro{idx}'].text())

    # required code for subscriptable objects
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)
