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
from PyQt5.QtWidgets import (QWidget, QFileDialog, QAbstractItemView)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from qtvcp import logger
from qtvcp.core import Action, Status, Info, Path, Tool

ACTION = Action()
STATUS = Status()
INFO = Info()
PATH = Path()
TOOL = Tool()
LOG = logger.getLogger(__name__)
LOG.setLevel(logger.INFO) # One of DEBUG, INFO, WARNING, ERROR, CRITICAL

VERSION = '1.5'


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
        self.dialog_code = 'CALCULATOR'
        self.text_dialog_code = 'KEYBOARD'

        if not self.create_connection():
            return None
        if 'tools' not in self.tables:
            LOG.debug("Creating tools table")
            self.create_tool_table()
        elif self.check_num_columns() == 9:
            self.query.prepare("ALTER TABLE tools RENAME COLUMN CPT TO DIA")
            if not self.query.exec_():
                LOG.debug(f'Rename column error: {self.query.lastError().text()}')
                return None
            self.query.prepare("ALTER TABLE tools ADD COLUMN Comment TEXT")
            if not self.query.exec_():
                LOG.debug(f'Add column error: {self.query.lastError().text()}')
                return None
 
        # set up the Qsql table model
        LOG.debug(f"Database tables: {self.tables}")
        self.tool_model = QtSql.QSqlTableModel()
        self.tool_model.setTable('tools')
        self.tool_model.setEditStrategy(QtSql.QSqlTableModel.OnFieldChange)
        rec = self.tool_model.record()
        for i in range(rec.count()):
            hdr = rec.fieldName(i)
            self.headers[hdr] = i
        self.tool_model.setSort(self.headers['TOOL'], Qt.AscendingOrder)
        self.tool_model.select()
        LOG.info(f"Using TOOL DATABASE version {VERSION}")

        self.init_tool_view()
        self.w.cmb_icon_select.setEnabled(False)

        # signal connections
        self.w.btn_enable_edit.clicked.connect(lambda state: self.w.cmb_icon_select.setEnabled(state))
        self.w.btn_export_table.pressed.connect(self.export_table)
        self.w.btn_export_database.pressed.connect(self.export_database)

    def hal_init(self):
        STATUS.connect('all-homed', lambda w: self.setEnabled(True))
        STATUS.connect('not-all-homed', lambda w, axis: self.setEnabled(False))
        STATUS.connect('general',self.return_value)

    def create_connection(self):
        db = QtSql.QSqlDatabase.addDatabase('QSQLITE')
        db.setDatabaseName(self.database)
        self.query = QtSql.QSqlQuery(db)
        if not db.open():
            LOG.debug(f"Database Error: {db.lastError().databaseText()}")
            return False
        self.tables = db.tables()
        return True

    # check if database is latest version
    def check_num_columns(self):
        self.query.prepare('SELECT * FROM tools LIMIT 1')
        if not self.query.exec_():
            LOG.debug(f'Query error: {self.query.lastError().text()}')
            return False
        column_count = self.query.record().count()
        return column_count
        
    def create_tool_table(self):
        query = '''
            CREATE TABLE tools (
                TOOL INTEGER DEFAULT 0,
                TIME REAL DEFAULT 0.0,
                RPM INTEGER DEFAULT 0,
                DIA REAL DEFAULT 0.0,
                LENGTH REAL DEFAULT 0.0,
                FLUTES INTEGER DEFAULT 0,
                FEED INTEGER DEFAULT 0,
                MFG TEXT DEFAULT "",
                ICON TEXT DEFAULT "not_found.png",
                Comment TEXT DEFAULT "");
            '''
        self.query.prepare(query)
        if self.query.exec_() is True:
            LOG.debug("Create tool table success")
        else:
            LOG.debug(f"Create tool table error: {self.query.lastError().text()}")

    def init_tool_view(self):
        self.tool_view.setModel(self.tool_model)
        delegate = StyleDelegate(self)
        for key, col in self.headers.items():
            if key == 'MFG' or key == 'ICON' or key == 'Comment':
                delegate.setAlignment(col, Qt.AlignLeft | Qt.AlignVCenter)
            else:
                delegate.setAlignment(col, Qt.AlignCenter)
        self.tool_view.setItemDelegate(delegate)
        self.tool_view.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.tool_view.setColumnWidth(self.headers['MFG'], 120)
        self.tool_view.setColumnWidth(self.headers['ICON'], 120)
        self.tool_view.setSelectionMode(QAbstractItemView.NoSelection)
        self.tool_view.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.tool_view.clicked.connect(self.showSelection)

    # called from handler during initialization
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
        # populate DIA and Comment columns with data from tool table
        tool_table = TOOL.GET_TOOL_ARRAY()
        for line in tool_table:
            row = self.get_index(line[0])
            self.tool_model.setData(self.tool_model.index(row, self.headers['DIA']), line[11])
            self.tool_model.setData(self.tool_model.index(row, self.headers['Comment']), line[15])
        self.tool_model.submitAll()
        self.tool_model.select()

    def update_tool_no(self, old, new):
        row = self.get_index(old)
        if row is None:
            LOG.debug(f"Index not found for tool {old}")
            return
        LOG.debug(f"Updating tool number from {old} to {new}")
        idx = self.tool_model.index(row, self.headers['TOOL'])
        self.tool_model.setData(idx, new)
        self.tool_model.select()

    # update tool database when the tool table is edited
    def update_tool_data(self, row, col):
        tool_table = TOOL.GET_TOOL_ARRAY()
        tool = tool_table[row][1]
        new_row = self.get_index(tool)
        if new_row is None:
            LOG.debug(f"Index not found for tool {tool}")
            return
        data = tool_table[row][col - 4]
        new_col = self.headers['DIA'] if col == 15 else self.headers['Comment']
        idx = self.tool_model.index(new_row, new_col)
        self.tool_model.setData(idx, data)
        self.tool_model.submitAll()
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

    # called during initialization or when the handler adds a new tool
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
    def showSelection(self, item):
        if not self.w.btn_enable_edit.isChecked(): return
        if item.row() == 0: return
        data = self.tool_model.data(item)
        col = item.column()
        field = self.tool_model.record().fieldName(col)
        if field == 'TOOL' or field == 'DIA' or field == 'Comment': return
        if field == 'ICON':
            self.current_row = item.row()
            self.w.cmb_icon_select.showPopup()
        elif field == 'MFG':
             self.callTextDialog(data, item)
        elif field in self.headers:
            self.callDialog(data, item)
        self.tool_view.clearSelection()
        self.tool_view.selectRow(self.selected_row)

    def callTextDialog(self, text, item):
        idx = self.tool_model.index(item.row(), self.headers['TOOL'])
        tool = self.tool_model.data(idx)
        mess = {'NAME': self.text_dialog_code,
                'ID': '_edit_table_',
                'PRELOAD': text,
                'TITLE': f'Tool {tool} Text Entry',
                'ITEM': item}
        LOG.debug('message sent:{}'.format (mess))
        ACTION.CALL_DIALOG(mess)

    def callDialog(self, data, item):
        idx = self.tool_model.index(item.row(), self.headers['TOOL'])
        tool = self.tool_model.data(idx)
        field = self.tool_model.record().fieldName(item.column())
        mess = {'NAME': self.dialog_code,
                'ID': '_edit_table_',
                'PRELOAD': data,
                'TITLE': f'Tool {tool} Data for {field}',
                'ITEM': item}
        LOG.debug(f'message sent:{mess}')
        ACTION.CALL_DIALOG(mess)

    def return_value(self, w, message):
        num = message['RETURN']
        code = bool(message.get('ID') == '_edit_table_')
        name = bool(message.get('NAME') == self.dialog_code)
        name2 = bool(message.get('NAME') == self.text_dialog_code)
        item = message.get('ITEM')

        if code:
            LOG.debug(f'message returned:{message}')
        if code and name and num is not None:
            field = self.tool_model.record().fieldName(item.column())
            if field in ['RPM', 'FLUTES', 'FEED']:
                num = int(num)
            else:
                num = round(float(num), 3)
            self.tool_model.setData(item, num)
        elif code and name2 and num is not None:
            self.tool_model.setData(item, num)

    def icon_select_activated(self, index):
        if not self.w.btn_enable_edit.isChecked(): return
        if index > 0:
            icon = self.w.cmb_icon_select.currentText()
            self.set_tool_icon(icon)
            self.w.cmb_icon_select.setCurrentIndex(0)

    def set_tool_icon(self, icon):
        row = self.current_row
        if row is None: return
        idx = self.tool_model.index(row, self.headers['ICON'])
        if not self.tool_model.setData(idx, icon):
            print(f"Setdata error - {self.tool_model.lastError().text()}")

## calls from host
    def set_checked_tool(self, tool):
        self.selected_row = self.get_index(tool)

    def set_edit_enable(self, state):
        if state:
            self.tool_view.setSelectionMode(QAbstractItemView.SingleSelection)
        else:
            self.tool_view.setSelectionMode(QAbstractItemView.NoSelection)

    def get_tool_data(self, tool, data):
        rtn = None
        row = self.get_index(tool)
        if not row is None:
            if data in self.headers.keys():
                rtn = self.tool_model.record(row).value(data)
        return rtn

    def export_table(self):
        tool_table = TOOL.GET_TOOL_ARRAY()
        headers = ["Tool", "Pocket"]
        for i in INFO.AVAILABLE_AXES:
            headers.append(i)
        headers.append("Diameter")
        headers.append("Comment")
        html = '''<html>
        <head>
        <title>QtDragon Tool Table</title>
        <style>
        table, th, td {
            border: 1px solid black;
        }
        </style>
        </head>
        <table>
        <caption>QtDragon Tool Table</caption>
        <thead>\n'''
        html += '<tr>'
        for hdr in headers:
            html += f'<td><center>{hdr}</center></td>'
        html += '</tr></thead>'
        html += '<tbody>\n'
        for row in tool_table:
            html += '<tr>'
            html += f'<td>{row[0]}</td>'
            html += f'<td>{row[1]}</td>'
            html += f'<td>{row[2]:.3f}</td>'
            html += f'<td>{row[3]:.3f}</td>'
            html += f'<td>{row[4]:.3f}</td>'
            if "A" in headers:
                html += f'<td>{row[5]:.3f}</td>'
            html += f'<td>{row[11]:.3f}</td>'
            html += f'<td>{row[15]}</td></tr>\n'
        html += '</tbody></table>\n'
        html += '</html>\n'

        saveName = self.get_file_save("Select Save Filename")
        if saveName != '':
            with open(saveName, 'w') as file:
                file.write(html)
            self.parent.add_status(f"Exported tool table to {saveName}")
        else:
            self.parent.add_status("Invalid filename specified")
        
    def export_database(self):
        html = '''<html>
        <head>
        <title>QtDragon Tool Database</title>
        <style>
        table, th, td {
            border: 1px solid black;
        }
        </style>
        </head>
        <table>
        <caption>QtDragon Tool Database</caption>
        <thead>\n'''
        html += '<tr>'
        for hdr in self.headers:
            html += f'<td><center>{hdr}</center></td>'
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
            html += '</tr>\n'
        html += '</tbody></table>\n'
        html += '</html>\n'

        saveName = self.get_file_save("Select Save Filename")
        if saveName != '':
            with open(saveName, 'w') as file:
                file.write(html)
            self.parent.add_status(f"Exported tool database to {saveName}")
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
        total_time = self.tool_model.record(row).value('TIME') + time
        total_time = f"{total_time:.3f}"
        idx = self.tool_model.index(row, self.headers['TIME'])
        self.tool_model.setData(idx, total_time)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    w = Tool_Database()
    w.show()
    sys.exit( app.exec_() )
