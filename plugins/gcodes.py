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
from qtpy import QtWidgets, uic
from qtpy.QtWidgets import QWidget, QLineEdit, QApplication
from qtpy.QtCore import Qt
from plugins import mdi_text as mdiText

HERE = os.path.dirname(os.path.abspath(__file__))

PLUGIN_INFO = {
    'mod_name' : 'gcodes',
    'class_name' : 'GCodes',
    'item_text' : 'GCODES',
    'version' : '2.0',
    'description' : '''Display a list of LinuxCNC G and M codes
Click on a G or M code to see an explanation of how to use it
'''
}


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
        self.setup_list()

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

    # required code for subscriptable objects
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)
