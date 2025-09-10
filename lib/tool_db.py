#!/usr/bin/env python3
# Copyright (c) 2025  Jim Sloot <persei802@gmail.com>
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
import sqlite3

from PyQt5 import uic
from PyQt5.QtSql import QSqlQuery, QSqlDatabase
from PyQt5.QtWidgets import QWidget, QTreeWidget, QTreeWidgetItem, QMenu
from PyQt5.QtGui import QPixmap, QDoubleValidator, QDragMoveEvent, QDropEvent, QFont, QCursor
from PyQt5.QtCore import Qt, QObject, QTimer, pyqtSignal

from qtvcp import logger
from qtvcp.core import Action, Status, Info, Path, Tool

try:
    from lib.event_filter import EventFilter
except ModuleNotFoundError:
    from event_filter import EventFilter

ACTION = Action()
STATUS = Status()
INFO = Info()
PATH = Path()
TOOL = Tool()
LOG = logger.getLogger(__name__)
LOG.setLevel(logger.DEBUG) # One of DEBUG, INFO, WARNING, ERROR, CRITICAL

VERSION = '1.6'
DB_NAME = 'tool_database.db'
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT =  0
WARNING =  1
ERROR = 2

tno_role = Qt.UserRole
name_role = Qt.UserRole + 1
group_role = Qt.UserRole + 2

# a promoted class to enable drag/drop funcionality for the tool tree
class ToolTree(QTreeWidget):
    item_moved = pyqtSignal(tuple)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QTreeWidget.InternalMove)
        self.setAutoScroll(True)
        self.setAutoScrollMargin(20)
        self.moved_item = None
        self.itemPressed.connect(self.on_item_pressed)
        self.scroll_timer = QTimer(self)
        self.scroll_timer.timeout.connect(self.auto_scroll)
        self.scroll_margin = 20
        self.scroll_speed = 5

    def on_item_pressed(self, item, column):
        self.moved_item = item

    def dragMoveEvent(self, event: QDragMoveEvent):
        target = self.itemAt(event.pos())
        if not target:
            event.ignore()
            return
        role = target.data(0, Qt.UserRole)
        if role == 'category':
            event.accept()
        else:
            event.ignore()

    def startDrag(self, supportedActions):
        self.scroll_timer.start(100)
        super().startDrag(supportedActions)

    def auto_scroll(self):
        global_pos = QCursor.pos()
        local_pos = self.viewport().mapFromGlobal(QCursor.pos())
        rect = self.viewport().rect()
        if not rect.contains(local_pos): return
        if local_pos.y() < self.scroll_margin:
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - self.scroll_speed)
        elif local_pos.y() > rect.height() - self.scroll_margin:
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() + self.scroll_speed)

    def dropEvent(self, event: QDropEvent):
        self.scroll_timer.stop()
        target = self.itemAt(event.pos())
        moved_item = self.moved_item
        self.moved_item = None
        if not moved_item: return
        if not target or target.data(0, Qt.UserRole) != 'category':
            event.ignore()
            return
        old_parent = moved_item.parent()
        if old_parent:
            old_parent.removeChild(moved_item)
        else:
            index = self.indexOfTopLevelItem(moved_item)
            if index >= 0:
                self.takeTopLevelItem(index)
        target.addChild(moved_item)
        target.setExpanded(True)
        new_group = target.text(0)
        tno = moved_item.data(0, tno_role)
        self.item_moved.emit((tno, new_group))

# a class to handle all interactions with the database
class SqlAgent(QObject):
    def __init__(self, db, tree, groups, parent=None):
        QObject.__init__(self)
        self.database = db
        self.tree = tree
        self.tree.setHeaderLabel('QtDragon Tool Categories')
        self.tree.setSortingEnabled(True)
        self.groups = groups
        self.item_dict = {}
        self.root_items = {}
        self.tree.item_moved.connect(self.update_item_group)

    def create_connection(self):
        db = QSqlDatabase.addDatabase('QSQLITE')
        db.setDatabaseName(self.database)
        if not db.open():
            LOG.debug(f"Database Error: {db.lastError().databaseText()}")
            return False
        return db.tables()

    def create_tool_table(self):
        query = QSqlQuery()
        query.prepare('''
            CREATE TABLE tools (
                TOOL     INTEGER PRIMARY KEY,
                NAME     TEXT DEFAULT "New Tool",
                CATEGORY TEXT DEFAULT "Misc",
                TLO REAL DEFAULT 0.0,
                DIA REAL DEFAULT 0.0,
                FLUTES   INTEGER DEFAULT 0,
                LENGTH   REAL DEFAULT 0.0,
                RPM      INTEGER DEFAULT 0,
                FEED     REAL DEFAULT 0.0,
                TIME     REAL DEFAULT 0.0,
                ICON     TEXT DEFAULT "not_found.png",
                MFG      TEXT DEFAULT "PN:")
            ''')
        if query.exec_() is True:
            LOG.debug("Create tool table success")
        else:
            LOG.debug(f"Create tool table error: {query.lastError().text()}")
        
    def build_tree(self):
        self.tree.clear()
        # create category root items
        for group in self.groups:
            self.create_root_item(group)
        query = QSqlQuery("SELECT TOOL, NAME, CATEGORY FROM tools")
        while query.next():
            tno = query.value(0)
            name = query.value(1)
            group = query.value(2)
            try:
                parent = self.root_items[group]
            except KeyError:
                parent = self.root_items['Misc']
                group = 'Misc'
            self.insert_tree_item(tno, name, group)
        self.tree.sortItems(0, Qt.AscendingOrder)
        self.tree.expandAll()

    def create_root_item(self, group):
        item = QTreeWidgetItem(self.tree, [group])
        item.setData(0, Qt.UserRole, 'category')
        item.setFlags(item.flags() & ~Qt.ItemIsDragEnabled)
#        item.setFont(0, QFont('Lato', 12))
        item.setExpanded(True)
        self.root_items[group] = item

    def delete_root_item(self, group):
        item = self.root_items[group]
        if item.childCount() > 0: return False
        self.root_items.pop(group)
        index = self.tree.indexOfTopLevelItem(item)
        if index >= 0:
            self.tree.takeTopLevelItem(index)
        return True

    def insert_tree_item(self, tno, name, group):
        parent = self.root_items[group]
        if parent:
            new_item = QTreeWidgetItem(parent, [f'T{tno} - {name}'])
            new_item.setData(0, tno_role, tno)
            new_item.setData(0, name_role, name)
            new_item.setData(0, group_role, group)
#            new_item.setFont(0, QFont('Lato', 11))
            self.item_dict[tno] = new_item

    def remove_tree_item(self, tno):
        item = self.item_dict[tno]
        self.item_dict.pop(tno)
        parent = item.parent()
        parent.removeChild(item)

    def refresh_tree_item(self, tno):
        item = self.item_dict[tno]
        tno = item.data(0, tno_role)
        name = item.data(0, name_role)
        item.setText(0, f'T{tno} - {name}')

    def set_selected(self, tno):
        if tno in self.item_dict.keys():
            item = self.item_dict[tno]
            self.tree.setCurrentItem(item)
            return item
        return None

    def update_item_group(self, data):
        tno, group = data
        query = QSqlQuery("UPDATE tools SET CATEGORY=? WHERE TOOL=?")
        query.addBindValue(group)
        query.addBindValue(tno)
        if not query.exec_():
            LOG.debug(f"Update tool category failed: {query.lastError().text()}")

## CRUD operations
    def add_tool(self, tno, tlo, dia, name):
        query = QSqlQuery("INSERT INTO tools (TOOL, NAME, TLO, DIA) VALUES (?, ?, ?, ?)")
        query.addBindValue(tno)
        query.addBindValue(name)
        query.addBindValue(tlo)
        query.addBindValue(dia)
        if not query.exec_():
            LOG.debug(f"Add tool failed: {query.lastError().text()}")
            return False
        return True

    def delete_tool(self, tno):
        query = QSqlQuery("DELETE FROM tools WHERE TOOL=?")
        query.addBindValue(tno)
        if not query.exec_():
            LOG.debug(f"Delete tool failed: {query.lastError().text()}")
            return False
        return True

    def get_tool_data(self, tno):
        query = QSqlQuery("SELECT * FROM tools WHERE TOOL=?")
        query.addBindValue(tno)
        if query.exec_() and query.next():
            rtn_dict = {
                'tool':   query.value(0),
                'name':   query.value(1),
                'group':  query.value(2),
                'tlo':    query.value(3),
                'dia':    query.value(4),
                'flutes': query.value(5),
                'length': query.value(6),
                'rpm':    query.value(7),
                'feed':   query.value(8),
                'time':   query.value(9),
                'icon':   query.value(10),
                'mfg':    query.value(11)}
            return rtn_dict
        return None

    def get_all_tools(self):
        tool_list = []
        query = QSqlQuery("SELECT TOOL FROM tools")
        while query.next():
            tool_list.append(query.value(0))
        return tool_list

    # this updates columns Z, DIA and Comment from the linuxcnc tool table
    def update_data(self, tno, data):
        query = QSqlQuery(f"UPDATE tools SET TLO=? , DIA=?, NAME=? WHERE TOOL = ?")
        query.addBindValue(data[0])
        query.addBindValue(data[1])
        query.addBindValue(data[2])
        query.addBindValue(tno)
        if not query.exec_():
            LOG.debug(f"Update data error: {query.lastError().text()}")
        # refresh tree item in case name changed
        item = self.item_dict[tno]
        item.setData(0, name_role, data[2])
        self.refresh_tree_item(tno)

    # this updates a table row with data from the UI parameters widget
    def update_tool(self, tno, data):
        query = QSqlQuery()
        query.prepare("""UPDATE tools
                         SET CATEGORY=?, FLUTES=?, LENGTH=?, RPM=?, FEED=?, TIME=?, ICON=?, MFG=?
                         WHERE TOOL=? """)
        for item in data:
            query.addBindValue(item)
        query.addBindValue(tno)
        if not query.exec_():
            LOG.debug(f"Update tool error: {query.lastError().text()}")
        # check if the category changed
        item = self.item_dict[tno]
        old_group = item.data(0, group_role)
        new_group = data[0]
        if old_group != new_group:
            tno = item.data(0, tno_role)
            name = item.data(0, name_role)
            self.remove_tree_item(tno)
            self.insert_tree_item(tno, name, new_group)

    def update_tool_number(self, tno, new):
        query = QSqlQuery("UPDATE tools SET TOOL=? WHERE TOOL=?")
        query.addBindValue(new)
        query.addBindValue(tno)
        if not query.exec_():
            LOG.debug(f"Update tool number error: {query.lastError().text()}")
            return False
        item = self.item_dict[tno]
        item.setData(0, tno_role, new)
        self.refresh_tree_item(tno)
        self.item_dict[new] = item
        self.item_dict.pop(tno)

    def update_tool_time(self, tno, time):
        query = QSqlQuery("UPDATE tools SET TIME=? WHERE TOOL=?")
        query.addBindValue(time)
        query.addBindValue(tno)
        if not query.exec_():
            LOG.debug(f"Update tool time error: {query.lastError().text()}")

    def tool_exists(self, tno):
        if tno in self.item_dict: return True
        return False

    def get_tool_count(self):
        return str(len(self.item_dict))

class Tool_Database(QWidget):
    def __init__(self, widgets, parent=None):
        super(Tool_Database, self).__init__()
        self.parent = parent
        self.w = widgets
        self.helpfile = 'tooldb_help.html'
        self.database = os.path.join(PATH.CONFIGPATH, DB_NAME)
        self.toolGroups = []
        self.unit_labels = ['tlo_unit', 'diameter_unit', 'flute_unit']
        self.dialog_code = 'CALCULATOR'
        self.text_dialog_code = 'KEYBOARD'
        self.default_style = ''
        self.red_border = "border: 2px solid red;"
        self.delay = 0
        self.selected_tool = 0
        self.old_geometry = []

        # Load the widgets UI file:
        self.filename = os.path.join(HERE, 'tool_db.ui')
        try:
            self.instance = uic.loadUi(self.filename, self)
        except AttributeError as e:
            LOG.debug(f"Error:  {e}")

        # populate comboboxes
        self.cmb_toolGroup.setEditable(True)
        self.cmb_toolGroup.setContextMenuPolicy(Qt.CustomContextMenu)
        if self.w.PREFS_:
            groups = self.w.PREFS_.getall('TOOL_GROUPS')
            if len(groups) > 0:
                for key in groups.keys():
                    group = groups[key]
                    self.toolGroups.append(group)
            else:
                self.toolGroups.append('Misc')
        self.cmb_toolGroup.addItems(self.toolGroups)
        path = os.path.join(PATH.CONFIGPATH, "tool_icons")
        if os.path.isdir(path):
            icons = os.listdir(path)
            icons.sort()
            for item in icons:
                if item.endswith(".png"):
                    self.cmb_icon.addItem(item)
        else:
            LOG.debug(f"No tool icons found in {path}")
        self.cmb_icon.addItem("undefined")
        self.set_unit_labels()
        
        # validators for lineEdits
        self.lineEdit_tlo.setValidator(QDoubleValidator(0, 999, 3))
        self.lineEdit_diameter.setValidator(QDoubleValidator(0, 999, 3))
        self.lineEdit_flute_length.setValidator(QDoubleValidator(0, 999, 3))
        self.lineEdit_feedrate.setValidator(QDoubleValidator(0, 9999, 3))

        # instantiate the sql agent and create tool table if necessary
        self.agent = SqlAgent(self.database, self.treeWidget, self.toolGroups)
        tables = self.agent.create_connection()
        if 'tools' not in tables:
            LOG.debug("Creating tools table")
            self.agent.create_tool_table()
        LOG.info(f"Using TOOL DATABASE version {VERSION}")

        # setup event filter to catch focus_in events
        self.event_filter = EventFilter(self)
        line_list = ['diameter', 'flute_length', 'feedrate', 'rpm', 'time_in_spindle']
        for item in line_list:
            self[f'lineEdit_{item}'].installEventFilter(self.event_filter)
        self.lineEdit_part_number.installEventFilter(self.event_filter)
        self.event_filter.set_line_list(line_list)
        self.event_filter.set_kbd_list(['part_number'])
        self.event_filter.set_parms(('_tooldb_', True))

        # signal connections
        self.cmb_toolGroup.lineEdit().returnPressed.connect(self.add_toolGroup)
        self.cmb_toolGroup.customContextMenuRequested.connect(self.show_menu)
        self.cmb_icon.activated.connect(self.display_tool_icon)
        self.btn_update.pressed.connect(self.update_tooldb)
        self.treeWidget.itemClicked.connect(self.on_item_clicked)
        self.chk_use_calc.stateChanged.connect(lambda state: self.event_filter.set_dialog_mode(state))
        self.chk_auto_update.stateChanged.connect(lambda state: self.enable_auto_update(state))

    def hal_init(self):
        STATUS.connect('all-homed', lambda w: self.setEnabled(True))
        STATUS.connect('not-all-homed', lambda w, axis: self.setEnabled(False))
        STATUS.connect('general',self.dialog_return)
        STATUS.connect('periodic', lambda w: self.auto_update())
        self.default_style = self.lineEdit_rpm.styleSheet()

    def closing_cleanup__(self):
        # first remove items under the TOOL_GROUPS section
        groups = self.w.PREFS_.getall('TOOL_GROUPS')
        if len(groups) > 0:
            for key in groups.keys():
                self.w.PREFS_.removepref(key, 'TOOL_GROUPS')
        # now add the new values
        for i, group in enumerate(self.toolGroups):
            group = self.toolGroups[i]
            self.w.PREFS_.putpref(f'group{i}', group, str, 'TOOL_GROUPS')

    # called from handler during initialization
    def load_tool_table(self, tlist):
        LOG.debug("Updating tool database")
        tools = []
        tool_table = TOOL.GET_TOOL_ARRAY()
        # look for tools to add
        db_list = self.agent.get_all_tools()
        for line in tool_table:
            tools.append(line[0])
            if line[0] in db_list: continue
            self.agent.add_tool(line[0], line[4], line[11], line[15])
        # look for tools to delete
        for tno in db_list:
            if tno in tools: continue
            self.agent.delete_tool(tno)
        # create the treeview
        self.agent.build_tree()
        self.lineEdit_tool_count.setText(self.agent.get_tool_count())

    def update_tool_no(self, old, new):
        old_exists = self.agent.tool_exists(old)
        new_exists = self.agent.tool_exists(new)
        if old_exists > 0 and not new_exists:
            self.agent.update_tool_number(old, new)
            return True
        return False

    # update tool database when the tool table is edited
    def update_tool_data(self, tno, data):
        if not self.agent.tool_exists(tno): return False
        self.agent.update_data(tno, data)
        return True

    def add_tool(self, tno=None):
        if tno is None: tno = -99
        if self.agent.tool_exists(tno): return False
        if self.agent.add_tool(tno, 0.0, 0.0, 'New Tool'):
            self.agent.insert_tree_item(tno, 'New Tool', 'Misc')
            self.lineEdit_tool_count.setText(self.agent.get_tool_count())
            return True
        return False

    def delete_tool(self, tno):
        if not self.agent.tool_exists(tno): return False
        if self.agent.delete_tool(tno):
            # now remove the tree items
            self.agent.remove_tree_item(tno)
            self.lineEdit_tool_count.setText(self.agent.get_tool_count())
            return True
        return False

## callbacks from widgets
    def add_toolGroup(self):
        group = self.cmb_toolGroup.currentText().strip()
        if group is None: return
        if self.cmb_toolGroup.findText(group) == -1:
            self.cmb_toolGroup.addItem(group)
            self.toolGroups.append(group)
            self.cmb_toolGroup.lineEdit().clear()
            self.cmb_toolGroup.setCurrentText(group)
            self.agent.create_root_item(group)
        else:
            self.parent.add_status("Duplicate tool category not permitted", WARNING)

    def show_menu(self, pos):
        menu = QMenu()
        remove_action = menu.addAction("Remove this group")
        action = menu.exec_(self.cmb_toolGroup.mapToGlobal(pos))
        if action == remove_action:
            index = self.cmb_toolGroup.currentIndex()
            if index >= 0:
                group = self.cmb_toolGroup.currentText()
                ok_to_delete = self.agent.delete_root_item(group)
                if ok_to_delete:
                    self.cmb_toolGroup.removeItem(index)
                    self.toolGroups.remove(group)
                else:
                    self.parent.add_status(f'Cannot remove category {group} until all tools have been moved out', WARNING)

    def on_item_clicked(self, item, col):
        if not item.parent(): return
        tno = item.data(0, tno_role)
        self.selected_tool = tno
        tool_data = self.agent.get_tool_data(tno)
        if tool_data is None: return
        try:
            self.lineEdit_number.setText(str(tool_data['tool']))
            self.cmb_toolGroup.setCurrentText(tool_data['group'])
            self.lineEdit_diameter.setText(str(tool_data['dia']))
            self.lineEdit_tlo.setText(str(tool_data['tlo']))
            self.spinBox_flutes.setValue(tool_data['flutes'])
            self.lineEdit_flute_length.setText(str(tool_data['length']))
            self.lineEdit_rpm.setText(str(tool_data['rpm']))
            self.lineEdit_feedrate.setText(str(tool_data['feed']))
            self.lineEdit_time_in_spindle.setText(self.min_to_hms(tool_data['time']))
            self.cmb_icon.setCurrentText(tool_data['icon'])
            self.lineEdit_part_number.setText(tool_data['mfg'])
            self.display_tool_icon()
        except Exception as e:
            LOG.debug(f'Item Clicked Error: , {e}')
        style = self.red_border if tool_data['tool'] < 0 else self.default_style
        self.lineEdit_number.setStyleSheet(style)
        
    # called when the UPDATE button is pressed
    def update_tooldb(self):
        item = self.treeWidget.currentItem()
        if item:
            tool_geometry = self.get_tool_geometry()
            if tool_geometry is None and not self.chk_auto_update.isChecked():
                self.parent.add_status('Error fetching tool geometry', WARNING)
                return
            if tool_geometry == self.old_geometry: return
            self.old_geometry = tool_geometry
            tno = item.data(0, tno_role)
            self.agent.update_tool(tno, tool_geometry[1:])
            self.lineEdit_tool_count.setText(self.agent.get_tool_count())

    def display_tool_icon(self):
        icon = self.cmb_icon.currentText()
        image_file = os.path.join(PATH.CONFIGPATH, 'tool_icons/' + icon)
        self.lbl_tool_icon.setPixmap(QPixmap(image_file))

    def enable_auto_update(self, state):
        self.btn_update.setEnabled(not state)
        self.delay = 0

## callbacks from STATUS
    def dialog_return(self, w, message):
        rtn = message['RETURN']
        name = message.get('NAME')
        code = bool(message.get('ID') == '_tooldb_')
        obj = message.get('OBJECT')
        next = message.get('NEXT', False)
        back = message.get('BACK', False)
        if code and name == self.dialog_code:
            obj.setStyleSheet(self.default_style)
            if rtn is None: return
            if obj.objectName().replace('lineEdit_', '') == 'rpm':
                obj.setText(f'{int(rtn)}')
            elif obj.objectName().replace('lineEdit_', '') == 'time_in_spindle':
                obj.setText(self.min_to_hms(rtn))
            else:
                obj.setText(f'{rtn:.3f}')
            # request for next input widget from linelist
            if next:
                newobj = self.event_filter.findNext()
                self.event_filter.show_calc(newobj, True)
            elif back:
                newobj = self.event_filter.findBack()
                self.event_filter.show_calc(newobj, True)
        elif code and name == self.text_dialog_code:
            obj.setStyleSheet(self.default_style)
            if rtn is None: return
            obj.setText(rtn)
        elif code and name == 'SAVE':
            if rtn is None:
                self.parent.add_status("Invalid filename specified")
                return
            with open(rtn, 'w') as file:
                file.write(self.html)
            self.parent.add_status(f"Exported tool table to {rtn}")

    def auto_update(self):
        if not self.chk_auto_update.isChecked() \
            or self.w.tabWidget_tools.currentIndex() != 1 \
            or not self.w.btn_tool.isChecked(): return
        self.delay += 1
        if self.delay == 10:
            self.delay = 0
            self.update_tooldb()

## calls from host
    def set_checked_tool(self, tno):
        item = self.agent.set_selected(tno)
        if item is None:
            self.parent.add_status(f'Set selected: item for tool {tno} not found', WARNING)
            return
        self.on_item_clicked(item, 0)

    def get_selected_tool(self):
        return self.selected_tool

    def get_tool_data(self, tno):
        record = self.agent.get_tool_data(tno)
        if record is None: return None
        return (record['length'], record['time'], record['icon'])

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
        self.html = html
        mess = {'NAME': 'SAVE',
                'ID': '_tooldb_',
                'TITLE': 'Save Program as',
                'FILENAME': '',
                'EXTENSIONS': 'HTML Files (*.html);;',
                'GEONAME': '__file_save',
                'OVERLAY': False}
        LOG.debug(f'message sent:{mess}')
        ACTION.CALL_DIALOG(mess)

    def update_tool_time(self, tno, time):
        record = self.agent.get_tool_data(tno)
        if record is None: return
        ptime = record['time']
        if ptime is not None:
            total_time = ptime + time
            self.lineEdit_time_in_spindle.setText(self.min_to_hms(total_time))
            self.agent.update_tool_time(tno, total_time)

## helper functions
    def get_tool_geometry(self):
        try:
            tool = int(self.lineEdit_number.text())
            toolgroup = self.cmb_toolGroup.currentText()
            flutes = self.spinBox_flutes.value()
            length = float(self.lineEdit_flute_length.text())
            rpm = int(self.lineEdit_rpm.text())
            feed = float(self.lineEdit_feedrate.text())
            time = self.get_time_format(self.lineEdit_time_in_spindle.text())
            icon = self.cmb_icon.currentText()
            part = self.lineEdit_part_number.text()
            rtn = (tool, toolgroup, flutes, length, rpm, feed, time, icon, part)
        except Exception as e:
            LOG.debug(f'Tool Geometry Error: , {e}')
            rtn = None
        return rtn

    def get_time_format(self, data):
        try:
            time = float(data)
        except ValueError:
            time = self.hms_to_min(data)
        return time
        
    def set_unit_labels(self):
        text = 'MM' if INFO.MACHINE_IS_METRIC else "IN"
        for item in self.unit_labels:
            self[f'lbl_{item}'].setText(text)
        self.lbl_feedrate_unit.setText(text + '/MIN')

    def min_to_hms(self, minutes):
        runtime = minutes * 60
        hours, remainder = divmod(int(runtime), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f'{hours:02d}:{minutes:02d}:{seconds:02d}'

    def hms_to_min(self, hms):
        rtime = hms.split(':')
        return (float(rtime[0]) * 60) + float(rtime[1]) + (float(rtime[2]) / 60)

    def run(self):
        if self.parent.config.get('debug'):
            self.parent.add_status('Running in demo mode')
        return 'done'

    # required code for subscriptable objects
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)

# This is just to get a visual of what the database manager looks like.
# It doesn't actually test anything.
class Testing:
    def __init__(self):
        self.config = {'debug': True}
        self.PREFS_ = False
        self.module = Tool_Database(self, self)
        self.module.show()

    def add_status(self, msg, level=None):
        print(msg)

    def run_test(self):
        result = self.module.run()
        print(f'Test result: {result}')
        
if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    test = Testing()
    test.run_test()
    sys.exit( app.exec_() )
