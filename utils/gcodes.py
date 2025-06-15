#!/usr/bin/env python3
# Copyright (c) 2025 Jim Sloot (persei802@gmail.com)
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
from PyQt5 import QtWidgets, uic
from PyQt5.QtWidgets import QWidget, QLineEdit, QApplication
from PyQt5.QtCore import Qt
from . import mdi_text as mdiText

HERE = os.path.dirname(os.path.abspath(__file__))


class GCodes(QWidget):
    def __init__(self, parent=None):
        super(GCodes, self).__init__()

        main_layout = QtWidgets.QHBoxLayout()
        right_pane = QtWidgets.QVBoxLayout()
        self.gcode_list = QtWidgets.QListWidget()
        self.gcode_description = QtWidgets.QPlainTextEdit()
        self.gcode_titles = QLineEdit()
        self.gcode_titles.setReadOnly(True)
        right_pane.addWidget(self.gcode_titles)
        right_pane.addWidget(self.gcode_description)
        main_layout.addWidget(self.gcode_list)
        main_layout.addLayout(right_pane)
        self.setLayout(main_layout)

    def setup_list(self):
        self.gcode_list.currentRowChanged.connect(self.list_row_changed)
        titles = mdiText.gcode_titles()
        for key in sorted(titles.keys()):
            self.gcode_list.addItem(key + ' ' + titles[key])

    def list_row_changed(self, row):
        line = self.gcode_list.currentItem().text()
        text = line.split(' ')[0]
        if text.startswith('G'):
            desc = mdiText.gcode_descriptions(text) or 'No Match'
        elif text.startswith('M'):
            desc = mdiText.mcode_descriptions(text) or 'No Match'
        else:
            desc = ''
        self.gcode_description.clear()
        self.gcode_description.insertPlainText(desc)

        if text:
            words = mdiText.gcode_words()
            if text in words:
                parm = text + ' '
                for index, value in enumerate(words[text], start=0):
                    parm += value
                self.gcode_titles.setText(parm)
            else:
                self.gcode_titles.clear()


class SmartMDI_delete(QWidget):
    def __init__(self, widgets=None):
        super(SmartMDI, self).__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        # Load the widgets UI file:
        self.filename = os.path.join(HERE, 'smart_mdi.ui')
        try:
            self.instance = uic.loadUi(self.filename, self)
        except AttributeError as e:
            print(e)

        self.w = widgets
        self.mdiSmartEntry = self.w.mdihistory.MDILine
        
        self.words = mdiText.gcode_words()
        self.titles = mdiText.gcode_titles()
        self.space_inserted = False
        
        self.mdiSmartButtonGroup.buttonClicked.connect(self.mdiSmartHandleKeys)
        self.btn_backspace.pressed.connect(self.mdiSmartHandleBackSpace)

    def mdiSmartHandleKeys(self, button):
        if button == self.btn_space:
            char = ' '
            self.space_inserted = True
        else:
            char = button.text()
        text = self.mdiSmartEntry.text() or '0'
        if text != '0':
            text += char
        else:
            text = char
        self.mdiSmartEntry.setText(text)
        if not self.space_inserted:
            self.mdiSmartSetLabels()

    def mdiSmartSetLabels(self):
        text = self.mdiSmartEntry.text() or '0'
        if text != '0':
            for idx in range(1,11):
                self[f'gcodeParameter_{idx}'].setText('')
            if text in self.words:
                for index, value in enumerate(self.words[text], start=1):
                    self[f'gcodeParameter_{index}'].setText(value)
            if text in self.titles:
                self.gcodeDescription.setText(self.titles[text])
            else:
                self.gcodeDescription.clear()
            if text.startswith('G'):
                self.gcodeHelpLabel.setPlainText(mdiText.gcode_descriptions(text))
            elif text.startswith('M'):
                self.gcodeHelpLabel.setPlainText(mdiText.mcode_descriptions(text))
            else:
                self.gcodeHelpLabel.clear()
        else:
            self.mdiSmartClear()

    def mdiSmartHandleBackSpace(self):
        if len(self.mdiSmartEntry.text()) > 0:
            if self.mdiSmartEntry.text()[-1:] == ' ':
                self.space_inserted = False
            text = self.mdiSmartEntry.text()[:-1]
            self.mdiSmartEntry.setText(text)
            if not self.space_inserted:
                self.mdiSmartSetLabels()

    def mdiSmartClear(self):
        for index in range(1,11):
            self[f'gcodeParameter_{index}'].setText('')
        self.gcodeDescription.clear()
        self.gcodeHelpLabel.clear()
        self.space_inserted = False

    # class patched from MDILine to show smart MDI panel
    def request_keyboard(self):
        self.show()
        target = self.w.groupBox_gcode
        target_bottom_left = target.mapToGlobal(target.rect().bottomLeft())
        x = target_bottom_left.x()
        y = target_bottom_left.y()
        self.move(x, y)

    def set_style(self, style):
        wstyle = style + "#widget_smart_mdi {background: #404040;}"
        self.setStyleSheet(wstyle)

    # required code for subscriptable objects
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)
