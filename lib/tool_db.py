#!/usr/bin/env python3
# Copyright (c) 2022  Jim Sloot <persei802@gmail.com>
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

from PyQt5 import QtCore, QtWidgets, QtSql, QtGui
from PyQt5.QtWidgets import (QWidget, QFileDialog, QInputDialog)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QTextDocument

from qtvcp import logger
from qtvcp.core import Status, Info, Path

STATUS = Status()
INFO = Info()
PATH = Path()
LOG = logger.getLogger(__name__)
LOG.setLevel(logger.INFO) # One of DEBUG, INFO, WARNING, ERROR, CRITICAL

VERSION = '1.2'


class StyleDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.alignments = {}
        self.highlight_color = QColor('#808080')

    def setAlignment(self, column, alignment):
        self.alignments[column] = alignment

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        col = index.column()
        if col in self.alignments:
            option.displayAlignment = self.alignments[col]
        if index.row() == self.parent.selected_row:
            option.backgroundBrush = self.highlight_color


class Tool_Database(QWidget):
    def __init__(self, widgets, parent=None):
        super(Tool_Database, self).__init__()
        self.parent = parent
        self.w = widgets
        self.headers = {}
        self.tool_view = widgets.tooldb_view
        self.helpfile = 'tooldb_help.html'
        self.database = os.path.join(PATH.CONFIGPATH, 'tool_database.db')
        self.tables = []
        self.query = None
        self.current_row = 0
        self.selected_row = None
        self.ndec = 3 if INFO.MACHINE_IS_METRIC else 4
        self.max_spindle_rpm = int(INFO.MAX_SPINDLE_SPEED)
        self.max_linear_velocity = int(INFO.MAX_TRAJ_VELOCITY)

        if not self.create_connection():
            return None
        if 'tools' not in self.tables:
            LOG.debug("Creating tools table")
            self.create_tool_table()
 
        LOG.debug(f"Database tables: {self.tables}")
        self.tool_model = QtSql.QSqlTableModel()
        self.tool_model.setTable('tools')
        self.tool_model.setEditStrategy(QtSql.QSqlTableModel.OnFieldChange)
        self.tool_model.select()
        LOG.info(f"Using TOOL DATABASE version {VERSION}")

        # fill in tool header dictionary
        rec = self.tool_model.record()
        for i in range(rec.count()):
            hdr = rec.fieldName(i)
            self.headers[hdr] = i
        self.init_tool_view()
        self.w.cmb_icon_select.setEnabled(False)

        # signal connections
        self.w.btn_enable_edit.clicked.connect(lambda state: self.w.cmb_icon_select.setEnabled(state))
        self.w.btn_export_data.pressed.connect(self.export_data)

    def hal_init(self):
        STATUS.connect('all-homed', lambda w: self.setEnabled(True))
        STATUS.connect('not-all-homed', lambda w, axis: self.setEnabled(False))

    def create_connection(self):
        db = QtSql.QSqlDatabase.addDatabase('QSQLITE')
        db.setDatabaseName(self.database)
        self.query = QtSql.QSqlQuery(db)
        if not db.open():
            LOG.debug(f"Database Error: {db.lastError().databaseText()}")
            return False
        self.tables = db.tables()
        return True

    def create_tool_table(self):
        if self.query.exec_(
            '''
            CREATE TABLE tools (
                TOOL INTEGER DEFAULT 0,
                TIME REAL DEFAULT 0.0,
                RPM INTEGER DEFAULT 0,
                CPT REAL DEFAULT 0.0,
                LENGTH REAL DEFAULT 0.0,
                FLUTES INTEGER DEFAULT 0,
                FEED INTEGER DEFAULT 0,
                MFG TEXT DEFAULT "",
                ICON TEXT DEFAULT "not_found.png"
            )
            '''
        ) is True:
            LOG.debug("Create tool table success")
        else:
            LOG.debug(f"Create tool table error: {self.query.lastError().text()}")

    def init_tool_view(self):
        self.tool_view.setModel(self.tool_model)
        delegate = StyleDelegate(self)
        for key, col in self.headers.items():
            if key == 'MFG' or key == 'ICON':
                delegate.setAlignment(col, Qt.AlignLeft | Qt.AlignVCenter)
            else:
                delegate.setAlignment(col, Qt.AlignCenter)
        self.tool_view.setItemDelegate(delegate)
        self.tool_view.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.tool_view.setColumnWidth(self.headers['MFG'], 150)
        self.tool_view.clicked.connect(self.showToolSelection)

    def update_tools(self, tools):
        LOG.debug("Updating tool model")
        # look for lines to add
        for tno in tools:
            row = self.get_index(tno)
            if row is None:
                self.add_tool(tno)
        # look for lines to delete
        delete_list = []
        for row in range(self.tool_model.rowCount()):
            tno = self.tool_model.record(row).value('TOOL')
            if tno is None: continue
            if tno not in tools:
                delete_list.append(tno)
        if delete_list:
            if len(delete_list) > 1: delete_list.reverse()
            for tno in delete_list:
                self.delete_tool(tno)
        self.tool_model.select()

    def update_tool_no(self, old, new):
        row = self.get_index(old)
        if row is None:
            LOG.debug(f"Index not found for tool {old}")
            return
        LOG.debug(f"Updating tool number from {old} to {new}")
        self.tool_model.setData(self.tool_model.index(row, self.headers['TOOL']), new)
        self.tool_model.select()

    def get_index(self, tno):
        count = self.tool_model.rowCount()
        found = None
        for row in range(count):
            tool = self.tool_model.record(row).value('TOOL')
            if tool == tno:
                found = row
                break
        return found

    def add_tool(self, tno):
        row = self.tool_model.rowCount()
        if self.tool_model.insertRows(row, 1): LOG.debug(f"Added tool {tno}")
        self.tool_model.setData(self.tool_model.index(row, self.headers['TOOL']), tno)
        self.tool_model.setData(self.tool_model.index(row, self.headers['TIME']), 0.0)
        self.tool_model.submitAll()
        self.tool_model.select()

    def delete_tool(self, tno):
        row = self.get_index(tno)
        if row is None: return
        if self.tool_model.removeRows(row, 1): LOG.debug(f"Deleted tool {tno}")
        self.tool_model.select()

## callbacks from widgets
    def showToolSelection(self, item):
        if not self.w.btn_enable_edit.isChecked(): return
        col = item.column()
        field = self.tool_model.record().fieldName(col)
        if field == 'TOOL': return
        if field == 'ICON':
            self.current_row = item.row()
            self.w.cmb_icon_select.showPopup()
        elif field in self.headers:
            self.callToolDialog(item, field)

    def callToolDialog(self, item, field):
        idx = self.tool_model.index(item.row(), self.headers['TOOL'])
        tool = self.tool_model.data(idx)
        if tool == 0: return
        idx = self.tool_model.index(item.row(), self.headers[field])
        header = f'Tool {tool} Data'
        preload = self.tool_model.data(idx)
        if field in ['TIME', 'CPT', 'LENGTH']:
            ret_val, ok = QInputDialog.getDouble(self, header, field, float(preload), decimals=self.ndec)
            if ok: self.tool_model.setData(idx, ret_val)
        elif field == 'RPM':
            ret_val, ok = QInputDialog.getInt(self, header, field, int(preload), 0, self.max_spindle_rpm, 100)
            if ok: self.tool_model.setData(idx, ret_val)
        elif field == 'FLUTES':
            ret_val, ok = QInputDialog.getInt(self, header, field, int(preload), 0, 8, 1)
            if ok: self.tool_model.setData(idx, ret_val)
        elif field == 'FEED':
            ret_val, ok = QInputDialog.getInt(self, header, field, int(preload), 0, self.max_linear_velocity, 100)
            if ok: self.tool_model.setData(idx, ret_val)
        elif field == 'MFG':
            ret_val, ok = QInputDialog.getText(self, header, field, text=preload)
            if ok: self.tool_model.setData(idx, ret_val)
        self.tool_model.submitAll()

    def icon_select_activated(self, index):
        if not self.w.btn_enable_edit.isChecked(): return
        if index > 0:
            icon = self.w.cmb_icon_select.currentText()
            self.set_tool_icon(icon)
            self.w.cmb_icon_select.setCurrentIndex(0)

## calls from host
    def set_checked_tool(self, tool):
        self.selected_row = self.get_index(tool)

    def set_tool_icon(self, icon):
        row = self.current_row
        if row is None: return
        idx = self.tool_model.index(row, self.headers['ICON'])
        if not self.tool_model.setData(idx, icon):
            print(f"Setdata error - {self.tool_model.lastError().text()}")

    def get_tool_data(self, tool, data):
        rtn = None
        row = self.get_index(tool)
        if not row is None:
            if data in self.headers.keys():
                rtn = self.tool_model.record(row).value(data)
        return rtn

    def export_data(self):
        doc = QTextDocument()
        html = '''<html>
        <head>
        <title>QtDragon Tool Database</title>\n
        <style>
        table, th, td {
            border: 1px solid black;
        }
        </style>
        </head>'''
        html += '<table><thead>'
        html += '<tr>'
        for hdr in self.headers:
            html += f'<th>{hdr}'
        html += '</tr></thead>'
        html += '<tbody>\n'
        rows = self.tool_model.rowCount()
        for row in range(rows):
            html += '<tr>'
            for hdr in self.headers:
                col = self.headers[hdr]
                idx = self.tool_model.index(row, col)
                data = str(self.tool_model.data(idx))
                html += f'<td>{data}</td>'
            html += '</tr>'
        html += '</tbody></table>'
        html += '</html>'
        doc.setHtml(html)

        saveName = self.get_file_save("Select Save Filename")
        if saveName != '':
            with open(saveName, 'w') as file:
                file.write(html)
            self.parent.add_status(f"Exported tool table to {saveName}")
        else:
            self.parent.add_status("Invalid filename specified")

    def get_file_save(self, caption):
        dialog = QFileDialog()
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        _filter = "HTML Files (*.html)"
        _dir = INFO.SUB_PATH
        fname, _ =  dialog.getSaveFileName(None, caption, _dir, _filter, options=options)
        if fname != '':
            fn, xn = os.path.splitext(fname)
            if os.path.basename(fn).startswith('.'):
                fname = ''
            elif xn != ".html":
                fname += ".html"
        return fname

    def update_tool_time(self, tno, time):
        row = self.get_index(tno)
        if row is None: return
        idx = self.tool_model.index(row, self.headers['TIME'])
        total_time = self.tool_model.record(row).value('TIME') + time
        total_time = f"{total_time:.3f}"
        self.tool_model.setData(idx, total_time)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    w = Tool_Database()
    w.initialize()
    w.show()
    style = 'tooldb.qss'
    if os.path.isfile(style):
        file = QtCore.QFile(style)
        file.open(QtCore.QFile.ReadOnly)
        styleSheet = QtCore.QTextStream(file)
        w.setStyleSheet("")
        w.setStyleSheet(styleSheet.readAll())
    sys.exit( app.exec_() )
