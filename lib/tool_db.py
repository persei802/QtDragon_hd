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
import csv

from PyQt5 import uic
from PyQt5.QtSql import QSqlQuery, QSqlDatabase
from PyQt5.QtWidgets import QWidget, QFileDialog, QLineEdit, QTreeWidget, QTreeWidgetItem, QMenu
from PyQt5.QtGui import QPixmap, QDoubleValidator, QFont, QCursor
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

VERSION = '2.0'
DB_NAME = 'tool_database.db'
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT =  0
WARNING =  1
ERROR = 2

grpRole = Qt.UserRole
tnoRole = Qt.UserRole + 1
midRole = Qt.UserRole + 2


# a promoted class to enable drag/drop funcionality for the tool tree
class ToolTree(QTreeWidget):
    item_moved = pyqtSignal(tuple)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAutoScroll(True)
        self.setAutoScrollMargin(48)
        self.scroll_timer = QTimer(self)
        self.scroll_timer.timeout.connect(self.auto_scroll)
        self.scroll_margin = 48
        self.scroll_speed = 5

    def auto_scroll(self):
        global_pos = QCursor.pos()
        local_pos = self.viewport().mapFromGlobal(QCursor.pos())
        rect = self.viewport().rect()
        if not rect.contains(local_pos): return
        if local_pos.y() < self.scroll_margin:
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - self.scroll_speed)
        elif local_pos.y() > rect.height() - self.scroll_margin:
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() + self.scroll_speed)

    def startDrag(self, supportedActions):
        self.scroll_timer.start(100)
        super().startDrag(supportedActions)

    def dragMoveEvent(self, event):
        indicator = self.dropIndicatorPosition()
        target = self.itemAt(event.pos())
        if target is None or target.parent() is not None:
            event.ignore()
            return
        if indicator == QTreeWidget.OnItem:
            if not target.data(0, grpRole):
                event.ignore()
                return
        event.accept()
        
    def dropEvent(self, event):
        self.scroll_timer.stop()
        indicator = self.dropIndicatorPosition()
        target = self.itemAt(event.pos())
        dragged_item = self.currentItem()

        if target is None or target.parent() is not None:
            event.ignore()
            return

        if indicator == QTreeWidget.OnItem:
            if not target.data(0, grpRole):
                event.ignore()
                return

        tool_no = dragged_item.data(0, tnoRole)
        group_id = target.data(0, grpRole)
#        disable super() to move the tree widgets programmatically
#        super().dropEvent(event)
        dragged_item.parent().removeChild(dragged_item)
        target.addChild(dragged_item)
        self.item_moved.emit((tool_no, group_id))


# a class to handle all interactions with the database
class SqlAgent(QObject):
    def __init__(self, db, tree, parent=None):
        QObject.__init__(self)
        self.database = db
        self.tree = tree
        self.tree.setHeaderLabel('QtDragon Tool Categories')
        self.tree.setSortingEnabled(True)
        self.group_items = {}
        self.tool_items = {}
        self.tree.item_moved.connect(self.update_item_group)

    def create_connection(self):
        db = QSqlDatabase.addDatabase('QSQLITE')
        db.setDatabaseName(self.database)
        if not db.open():
            LOG.debug(f"Database Error: {db.lastError().databaseText()}")
            return False
        QSqlQuery().exec_("PRAGMA foreign_keys = ON")
        return db.tables()

    def create_tool_table(self):
        query = QSqlQuery()
        query.prepare('''
            CREATE TABLE tools (
                TOOL     INTEGER PRIMARY KEY,
                NAME     TEXT DEFAULT "New Tool",
                group_id INTEGER NOT NULL,
                TLO REAL DEFAULT 0.0,
                DIA REAL DEFAULT 0.0,
                FLUTES   INTEGER DEFAULT 0,
                LENGTH   REAL DEFAULT 0.0,
                TIME     REAL DEFAULT 0.0,
                ICON     TEXT DEFAULT "not_found.png",
                MFG      TEXT DEFAULT "PN:",
                FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE RESTRICT)
            ''')
        if query.exec_() is True:
            LOG.debug("Create tool table success")
        else:
            LOG.debug(f"Create tool table error: {query.lastError().text()}")
        
    def create_group_table(self):
        query = QSqlQuery()
        query.prepare('''
            CREATE TABLE groups (
                id    INTEGER PRIMARY KEY,
                NAME  TEXT NOT NULL UNIQUE)
            ''')
        if not query.exec_():
            LOG.debug(f"Create groups table error: {query.lastError().text()}")
            return None
        LOG.debug("Create groups table success")
        self.add_group_to_table('Misc')
        
    def create_material_table(self):
        query = QSqlQuery()
        query.prepare('''
            CREATE TABLE materials (
                id    INTEGER PRIMARY KEY,
                NAME  TEXT NOT NULL UNIQUE)
            ''')
        if not query.exec_():
            LOG.debug(f"Create materials table error: {query.lastError().text()}")
            return None
        LOG.debug("Create materials table success")
        self.add_material_to_table('None')

    def create_params_table(self):
        query = QSqlQuery()
        query.prepare('''
            CREATE TABLE params (
                tool_no     INTEGER NOT NULL,
                material_id INTEGER NOT NULL,
                RPM         INTEGER DEFAULT 0,
                FEED        REAL DEFAULT 0.0,
                STEPOVER    REAL DEFAULT 0.0,
                DEPTH       REAL DEFAULT 0.0,
                PRIMARY KEY(tool_no, material_id),
                FOREIGN KEY(tool_no) REFERENCES tools(TOOL) ON DELETE CASCADE,
                FOREIGN KEY(material_id) REFERENCES materials(id) ON DELETE CASCADE)
            ''')
        if query.exec_() is True:
            LOG.debug("Create params table success")
        else:
            LOG.debug(f"Create params table error: {query.lastError().text()}")

    def build_tree(self):
        self.tree.clear()
        # create group items
        query = QSqlQuery("SELECT id, NAME FROM groups")
        while query.next():
            group_id = query.value(0)
            group_name = query.value(1)
            group_item = self.create_group_item(group_name, group_id)
            self.populate_tools(group_id)
        self.tree.sortItems(0, Qt.AscendingOrder)
        self.tree.expandAll()

    def populate_tools(self, group_id):
        query = QSqlQuery()
        query.prepare("SELECT TOOL, NAME FROM tools WHERE group_id=?")
        query.addBindValue(group_id)
        query.exec_()
        while query.next():
            tool_num = query.value(0)
            tool_name = query.value(1)
            tool_item = self.create_tool_item(group_id, tool_num, tool_name)
            self.populate_materials(tool_item, tool_num)

    def populate_materials(self, parent, tool_num):
        query = QSqlQuery()
        query.prepare("""
            SELECT
                materials.id,
                materials.NAME
            FROM params
            JOIN materials ON materials.id = params.material_id
            WHERE params.tool_no = ?
            """)
        query.addBindValue(tool_num)
        if not query.exec_():
            LOG.debug(f"SELECT material params failed: {query.lastError().text()}")
            return None
        while query.next():
            material_id = query.value(0)
            material = query.value(1)
            material_item = self.create_material_item(parent, material, material_id)

    def create_group_item(self, name, group_id):
        group_item = QTreeWidgetItem(self.tree)
        group_item.setText(0, name)
        group_item.setData(0, grpRole, group_id)
        group_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDropEnabled)
        self.group_items[group_id] = group_item
        return group_item

    def create_tool_item(self, group_id, tno, name):
        parent = self.group_items[group_id]
        tool_item = QTreeWidgetItem(parent)
        tool_item.setText(0, f'T{tno} - {name}')
        tool_item.setData(0, tnoRole, tno)
        tool_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
        self.tool_items[tno] = tool_item
        return tool_item

    def create_material_item(self, parent, name, material_id):
        material_item = QTreeWidgetItem(parent)
        material_item.setText(0, name)
        material_item.setData(0, midRole, material_id)
        material_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        if name == 'None':
            material_item.setHidden(True)
        return material_item

    def remove_tree_item(self, item, tno=None):
        group_id = item.data(0, grpRole)
        tool_no = item.data(0, tnoRole)
        material_id = item.data(0, midRole)
        if group_id:
            if item.childCount() > 0: return False
            idx = self.tree.indexOfTopLevelItem(item)
            if idx >= 0:
                self.tree.takeTopLevelItem(idx)
            self.group_items.pop(group_id)
            query = QSqlQuery(f"DELETE FROM groups WHERE id={group_id}")
        elif tool_no:
            item.parent().removeChild(item)
            self.tool_items.pop(tool_no)
            self.delete_tool(tool_no)
        elif material_id:
            item.parent().removeChild(item)
            query = QSqlQuery(f'DELETE FROM params WHERE tool_no={tno} AND material_id={material_id}')
        else: return False
        return True

    def update_item_group(self, data):
        tool_no, group_id = data
        query = QSqlQuery()
        query.prepare("UPDATE tools SET group_id=? WHERE TOOL=?")
        query.addBindValue(group_id)
        query.addBindValue(tool_no)
        if not query.exec_():
            LOG.debug(f"Update tool group failed: {query.lastError().text()}")

## CRUD operations
    def add_tool_to_table(self, group_id, tno, tlo, dia, name):
        query = QSqlQuery()
        query.prepare("""
            INSERT INTO tools
                (group_id, TOOL, NAME, TLO, DIA)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(TOOL) DO NOTHING
        """)
        query.addBindValue(group_id)
        query.addBindValue(tno)
        query.addBindValue(name)
        query.addBindValue(tlo)
        query.addBindValue(dia)
        if not query.exec_():
            LOG.debug(f"Add tool failed: {query.lastError().text()}")
            return None
        if query.numRowsAffected() == 0:
            LOG.debug(f'Add tool {tno} conflict')
            return None
        return query.lastInsertId()

    def delete_tool(self, tno):
        query = QSqlQuery("DELETE FROM tools WHERE TOOL=?")
        query.addBindValue(tno)
        if not query.exec_():
            LOG.debug(f"Delete tool failed: {query.lastError().text()}")
            return None
        return True

    def add_material_to_table(self, material):
        query = QSqlQuery()
        query.prepare("""
            INSERT INTO materials (NAME) VALUES(?)
            ON CONFLICT (NAME) DO UPDATE SET NAME=excluded.NAME
            """)
        query.addBindValue(material)
        if not query.exec_():
            LOG.debug(f"Add material error: {query.lastError().text()}")
            return None
        material_id = query.lastInsertId()
        return material_id

    def add_group_to_table(self, group):
        query = QSqlQuery()
        query.prepare("INSERT INTO groups (NAME) VALUES(?)")
        query.addBindValue(group)
        if not query.exec_():
            LOG.debug(f"Add group failed: {query.lastError().text()}")
            return None
        group_id = query.lastInsertId()
        self.create_group_item(group, group_id)
        return group_id

    def remove_material(self, material):
        query = QSqlQuery()
        query.prepare("DELETE FROM materials WHERE NAME=?")
        query.addBindValue(material)
        if not query.exec_():
            LOG.debug(f"Delete materials failed: {query.lastError().text()}")
            return None
        return True

    def get_tool_data(self, tool_no):
        query = QSqlQuery()
        query.prepare("SELECT * FROM tools WHERE TOOL=?")
        query.addBindValue(tool_no)
        if query.exec_() and query.next():
            rtn_dict = {
                'tool':   query.value(0),
                'name':   query.value(1),
                'gid':    query.value(2),
                'tlo':    query.value(3),
                'dia':    query.value(4),
                'flutes': query.value(5),
                'length': query.value(6),
                'time':   query.value(7),
                'icon':   query.value(8),
                'mfg':    query.value(9)}
            return rtn_dict
        LOG.debug(f"Get tool data failed: {query.lastError().text()}")
        return None

    def get_material_data(self, tool_no, material_id):
        query = QSqlQuery()
        query.prepare("SELECT * FROM params WHERE tool_no=? AND material_id=?")
        query.addBindValue(tool_no)
        query.addBindValue(material_id)
        if query.exec_() and query.next():
            rtn_dict = {
                'tool_no':     query.value(0),
                'material_id': query.value(1),
                'rpm':         query.value(2),
                'feed':        query.value(3),
                'stepover':    query.value(4),
                'depth':       query.value(5)}
            return rtn_dict
        LOG.debug(f"No material found: {query.lastError().text()}")
        return None

    def get_group_id(self, name):
        for group_id, item in self.group_items.items():
            if item.text(0) == name:
                return group_id
        return None

    def get_material_id(self, name):
        query = QSqlQuery()
        query.prepare("SELECT id FROM materials WHERE NAME=?")
        query.addBindValue(name)
        if query.exec_() and query.next():
            return query.value(0)
        else:
            LOG.debug('Get material id Error - {query.lastError().text()}')
            return None

    def get_all_tools(self):
        tool_list = []
        query = QSqlQuery("SELECT TOOL FROM tools")
        while query.next():
            tool_list.append(query.value(0))
        return tool_list

    def get_all_materials(self):
        material_list = []
        query = QSqlQuery("SELECT NAME FROM materials")
        while query.next():
            material_list.append(query.value(0))
        return material_list

    # this updates columns Z, DIA and Comment from the linuxcnc tool table
    def update_tool_table(self, tool_no, data):
        query = QSqlQuery()
        query.prepare("UPDATE tools SET TLO=? , DIA=?, NAME=? WHERE TOOL = ?")
        query.addBindValue(data[0])
        query.addBindValue(data[1])
        query.addBindValue(data[2])
        query.addBindValue(tool_no)
        if not query.exec_():
            LOG.debug(f"Update tool table error: {query.lastError().text()}")
            return None
        # refresh tree item in case name changed
        item = self.tool_items[tool_no]
        tno = item.data(0, tnoRole)
        name = f'T{tno} - {data[2]}'
        item.setText(0, name)
        return True

    # this updates a table row with data from the UI tool data values
    def update_tool_data(self, data, tool_no):
        query = QSqlQuery()
        query.prepare("""
            UPDATE tools
            SET FLUTES=?, LENGTH=?, TIME=?, ICON=?, MFG=?
            WHERE TOOL=?
        """)
        for item in data:
            query.addBindValue(item)
        query.addBindValue(tool_no)
        if not query.exec_():
            LOG.debug(f"Update tool data error: {query.lastError().text()}")
        
    def update_material_data(self, data, tool_no, material_id):
        query = QSqlQuery()
        query.prepare("""
            INSERT INTO params (
                tool_no,
                material_id,
                RPM,
                FEED,
                STEPOVER,
                DEPTH)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(tool_no, material_id)
            DO UPDATE SET
                RPM=excluded.RPM,
                FEED=excluded.FEED,
                STEPOVER=excluded.STEPOVER,
                DEPTH=excluded.DEPTH
        """)
        query.addBindValue(tool_no)
        query.addBindValue(material_id)
        for value in data:
            query.addBindValue(value)
        if not query.exec_():
            LOG.debug(f"Update material Error: {query.lastError().text()}")
            return None
        if query.numRowsAffected() == 0:
            LOG.debug('Update material conflict')
            return None
        return query.lastInsertId()

    def update_tool_number(self, tool_no, new):
        query = QSqlQuery()
        query.prepare("UPDATE tools SET TOOL=? WHERE TOOL=?")
        query.addBindValue(new)
        query.addBindValue(tool_no)
        if not query.exec_():
            LOG.debug(f"Update tool number error: {query.lastError().text()}")
            return False
        item = self.tool_items[tool_no]
        item.setData(0, tnoRole, new)
        text = item.text(0).split(' ')
        text[0] = f'T{new}'
        new_name = ' '.join(text)
        item.setText(0, new_name)
        self.tool_items[new] = item
        self.tool_items.pop(tool_no)
        return True

    def update_tool_time(self, tool_no, time):
        query = QSqlQuery()
        query.prepare("UPDATE tools SET TIME=? WHERE TOOL=?")
        query.addBindValue(time)
        query.addBindValue(tool_no)
        if not query.exec_():
            LOG.debug(f"Update tool time error: {query.lastError().text()}")
            return None
        return True

class Tool_Database(QWidget):
    def __init__(self, parent=None):
        super(Tool_Database, self).__init__()
        self.parent = parent
        self.helpfile = 'tooldb_help.html'
        self.database = os.path.join(PATH.CONFIGPATH, DB_NAME)
        self.unit_labels = ['tlo_unit', 'diameter_unit', 'flute_unit', 'stepover_unit', 'depth_unit']
        self.dialog_code = 'CALCULATOR'
        self.text_dialog_code = 'KEYBOARD'
        self.geometry = None
        self.default_style = ''
        self.red_border = "border: 2px solid red;"
        self.delay = 0

        # Load the widgets UI file:
        self.filename = os.path.join(HERE, 'tool_db.ui')
        try:
            self.instance = uic.loadUi(self.filename, self)
        except AttributeError as e:
            LOG.debug(f"Error:  {e}")

        # validators for lineEdits
        self.lineEdit_tlo.setValidator(QDoubleValidator(0, 999, 3))
        self.lineEdit_diameter.setValidator(QDoubleValidator(0, 999, 3))
        self.lineEdit_flute_length.setValidator(QDoubleValidator(0, 999, 3))
        self.lineEdit_feedrate.setValidator(QDoubleValidator(0, 9999, 3))
        self.lineEdit_stepover.setValidator(QDoubleValidator(0, 999, 3))
        self.lineEdit_depth.setValidator(QDoubleValidator(0, 999, 3))

        # setup event filter to catch focus_in events
        self.event_filter = EventFilter(self)
        line_list = ['flute_length', 'num_flutes', 'time_in_spindle', 'rpm', 'feedrate', 'stepover', 'depth']
        for item in line_list:
            self[f'lineEdit_{item}'].installEventFilter(self.event_filter)
        self.lineEdit_part_number.installEventFilter(self.event_filter)
        self.event_filter.set_line_list(line_list)
        self.event_filter.set_kbd_list(['part_number'])
        self.event_filter.set_parms(('_tooldb_', True))

        # signal connections
        self.btn_update_tool.pressed.connect(self.btn_update_pressed)
        self.treeWidget.itemClicked.connect(self.on_item_clicked)
        self.chk_use_calc.stateChanged.connect(lambda state: self.event_filter.set_dialog_mode(state))
        self.chk_expand_all.stateChanged.connect(lambda state: self.expand_all(state))
        self.cmb_icon.activated.connect(self.display_tool_icon)
        
        # instantiate the sql agent and create required tables if necessary
        self.agent = SqlAgent(self.database, self.treeWidget)
        tables = self.agent.create_connection()
        LOG.debug(f"DB tables: {tables}")
        if 'groups' not in tables:
            LOG.debug("Creating groups table")
            self.agent.create_group_table()
        if 'materials' not in tables:
            LOG.debug("Creating materials table")
            self.agent.create_material_table()
        if 'tools' not in tables:
            LOG.debug("Creating tools table")
            self.agent.create_tool_table()
        if 'params' not in tables:
            LOG.debug("Creating parameters table")
            self.agent.create_params_table()
        LOG.info(f"Using TOOL DATABASE version {VERSION}")

        self.set_unit_labels()
        self.agent.build_tree()
        self.init_comboboxes()

    def hal_init(self):
        STATUS.connect('all-homed', lambda w: self.setEnabled(True))
        STATUS.connect('not-all-homed', lambda w, axis: self.setEnabled(False))
        STATUS.connect('tool-in-spindle-changed', lambda w, tool: self.set_selected_item(tool))
        STATUS.connect('general', self.dialog_return)
        self.default_style = self.lineEdit_rpm.styleSheet()

    def closing_cleanup__(self):
        pass

    def init_comboboxes(self):
        # icon combobox
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
        # group combobox
        self.cmb_group.setEditable(True)
        self.cmb_group.setContextMenuPolicy(Qt.CustomContextMenu)
        self.cmb_group.lineEdit().returnPressed.connect(self.add_group)
        self.cmb_group.customContextMenuRequested.connect(self.show_groupMenu)
        for item in self.agent.group_items.values():
            self.cmb_group.addItem(item.text(0))
        # material combobox
        self.cmb_material.setEditable(True)
        self.cmb_material.setContextMenuPolicy(Qt.CustomContextMenu)
        self.cmb_material.lineEdit().returnPressed.connect(self.add_material)
        self.cmb_material.customContextMenuRequested.connect(self.show_materialMenu)
        self.cmb_material.addItems(self.agent.get_all_materials())

    # called from handler during initialization
    def load_tool_table(self, tlist):
        LOG.info("Updating tool database")
        group_id = self.agent.get_group_id('Misc')
        tools = []
        tool_table = TOOL.GET_TOOL_ARRAY()
        # look for tools to add
        db_list = self.agent.get_all_tools()
        for line in tool_table:
            tools.append(line[0])
            if line[0] in db_list: continue
            tool_no = self.agent.add_tool_to_table(group_id, line[0], line[4], line[11], line[15])
            self.agent.create_tool_item(group_id, line[0], line[15])
        # look for tools to delete
        for tno in db_list:
            if tno in tools: continue
            self.delete_tool(tno)
        LOG.info("Successfully built tool tree")

## callbacks from widgets
    def add_group(self):
        group_name = self.cmb_group.currentText().strip()
        if not group_name: return
        for group in self.agent.group_items.values():
            if group.text(0) == group_name:
                self.parent.add_status(f'{group_name} already exists in database', WARNING)
                return
        self.cmb_group.clearFocus()
        group_id = self.agent.add_group_to_table(group_name)

    def add_material(self):
        material = self.cmb_material.currentText().strip()
        if not material: return
        self.cmb_material.clearFocus()
        material_id = self.agent.add_material_to_table(material)
        current_item = self.treeWidget.currentItem()
        tool_no = current_item.data(0, tnoRole)
        if tool_no:
            tool = current_item.data(0, tnoRole)
            new_item = self.agent.create_material_item(current_item, material, material_id)
            self.agent.update_material_data((0, 0, 0, 0), tool_no, material_id)
            self.parent.add_status(f'Added {material} to tool {tool}')

    # treeview item clicked
    def on_item_clicked(self, item, col):
        group_id = item.data(0, grpRole)
        tool_no = item.data(0, tnoRole)
        material_id = item.data(0, midRole)
        # fetch data from tools table
        tool_data = None
        material_data = None
        if group_id:
            self.cmb_group.setCurrentText(item.text(0))
        elif tool_no is not None:
            self.agent.tool_items[tool_no].setExpanded(True)
            tool_data = self.agent.get_tool_data(tool_no)
            material_id = self.agent.get_material_id('None')
            self.cmb_material.setCurrentText('None')
        elif material_id:
            tool_no = item.parent().data(0, tnoRole)
            tool_data = self.agent.get_tool_data(tool_no)
            self.cmb_material.setCurrentText(item.text(0))
            material_data = self.agent.get_material_data(tool_no, material_id)

        if tool_data:
            self.lineEdit_number.setText(str(tool_data['tool']))
            self.lineEdit_diameter.setText(str(tool_data['dia']))
            self.lineEdit_tlo.setText(str(tool_data['tlo']))
            self.lineEdit_num_flutes.setText(str(tool_data['flutes']))
            self.lineEdit_flute_length.setText(str(tool_data['length']))
            self.lineEdit_time_in_spindle.setText(self.min_to_hms(tool_data['time']))
            self.cmb_icon.setCurrentText(tool_data['icon'])
            self.lineEdit_part_number.setText(tool_data['mfg'])
            self.display_tool_icon()
            style = self.red_border if tool_data['tool'] < 0 else self.default_style
            self.lineEdit_number.setStyleSheet(style)
            group_id = tool_data['gid']
            group_name = self.agent.group_items[group_id].text(0)
            self.cmb_group.setCurrentText(group_name)

        if material_data:
            self.lineEdit_rpm.setText(str(material_data['rpm']))
            self.lineEdit_feedrate.setText(str(material_data['feed']))
            self.lineEdit_stepover.setText(str(material_data['stepover']))
            self.lineEdit_depth.setText(str(material_data['depth']))
        else:
            self.clear_parm_lines()

    # called when the UPDATE_TOOL button is pressed
    def btn_update_pressed(self):
        current_item = self.treeWidget.currentItem()
        tool_no = current_item.data(0, tnoRole)
        material_id = current_item.data(0, midRole)
        if tool_no:
            material_id = self.agent.get_material_id('None')
            old_group_id = current_item.parent().data(0, grpRole)
        elif material_id:
            tool_no = current_item.parent().data(0, tnoRole)
            old_group_id = current_item.parent().parent().data(0, grpRole)
        else: return
        self.update_tool_data(tool_no)
        # check if tool item was moved to new group
        new_group_id = self.agent.get_group_id(self.cmb_group.currentText())
        if not current_item.data(0, midRole) and (old_group_id != new_group_id):
            new_parent = self.agent.group_items[new_group_id]
            self.agent.update_item_group((tool_no, new_group_id))
            idx = current_item.parent().indexOfChild(current_item)
            current_item.parent().takeChild(idx)
            new_parent.addChild(current_item)
        self.update_material_data(tool_no, material_id)

    def update_tool_data(self, tool_no):
        try:
            flutes = int(self.lineEdit_num_flutes.text())
            length = float(self.lineEdit_flute_length.text())
            time = self.get_time_format(self.lineEdit_time_in_spindle.text())
            icon = self.cmb_icon.currentText()
            part = self.lineEdit_part_number.text()
        except Exception as e:
            LOG.debug(f'Update tool data Error: , {e}')
            return
        data = (flutes, length, time, icon, part)
        self.agent.update_tool_data(data, tool_no)
        
    def update_material_data(self, tool_no, material_id):
        try:
            rpm = int(self.lineEdit_rpm.text())
            feed = float(self.lineEdit_feedrate.text())
            stepover = float(self.lineEdit_stepover.text())
            depth = float(self.lineEdit_depth.text())
        except Exception as e:
            LOG.debug(f'Invalid material data: {e}')
            return
        data = (rpm, feed, stepover, depth)
        self.agent.update_material_data(data, tool_no, material_id)
        
    def display_tool_icon(self):
        icon = self.cmb_icon.currentText()
        image_file = os.path.join(PATH.CONFIGPATH, 'tool_icons/' + icon)
        self.lbl_tool_icon.setPixmap(QPixmap(image_file))

## callbacks from STATUS
    def set_selected_item(self, tool_no):
        item = self.agent.tool_items[tool_no]
        self.treeWidget.setCurrentItem(item)
        self.on_item_clicked(item, 0)

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

## calls from host
    def add_tool(self, tno=None):
        if tno is None: tno = -99
        group_id = self.agent.get_group_id('Misc')
        tool_no = self.agent.add_tool_to_table(group_id, tno, 0.0, 0.0, 'New Tool')
        if tool_no:
            tool_item = self.agent.create_tool_item(group_id, tno, 'New Tool')
            return True
        return False

    def delete_tool(self, tno):
        try:
            tool_item = self.agent.tool_items[tno]
            self.agent.remove_tree_item(tool_item)
        except KeyError:
            return False
        return True

    # update tool database when the tool table is edited
    def update_tool_table(self, tno, data):
        return self.agent.update_tool_table(tno, data)

    def update_tool_no(self, old, new):
        return self.agent.update_tool_number(old, new)

    def update_tool_time(self, tno, time):
        record = self.agent.get_tool_data(tno)
        if record is None: return
        ptime = record['time']
        if ptime is not None:
            total_time = round(ptime + time, 3)
            self.lineEdit_time_in_spindle.setText(self.min_to_hms(total_time))
            self.update_tool_data(tno)

    def get_selected_tool(self):
        selected_item = self.treeWidget.currentItem()
        if selected_item.data(0, tnoRole):
            return selected_item.data(0, tnoRole)
        if selected_item.data(0, midRole):
            return selected_item.parent().data(0, tnoRole)
        return None

    def get_tool_count(self):
        return str(len(self.agent.tool_items))

    def get_tool_data(self, tno):
        record = self.agent.get_tool_data(tno)
        return record

    def export_table(self):
        dialog = QFileDialog(self)
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        dialog.setFileMode(QFileDialog.AnyFile)
        dialog.setDirectory(os.path.expanduser('~/linuxcnc/setup_files'))
        dialog.setNameFilters(["csv Files (*.csv)", "html files (*.html)", "All Files (*)"])
        dialog.setDefaultSuffix("html")
        for le in dialog.findChildren(QLineEdit):
            le.setCompleter(None)
        if self.geometry:
            dialog.restoreGeometry(self.geometry)
        if not dialog.exec_(): return
        self.geometry = dialog.saveGeometry()
        fileName = dialog.selectedFiles()[0]
        if fileName.endswith('.csv'):
            if self.export_to_csv(fileName):
                self.parent.add_status(f"Exported Tools to {fileName}")
        elif fileName.endswith('.html'):
            if self.export_to_html(fileName):
                self.parent.add_status(f'Exported Tools to {fileName}')
        else:
            self.parent.add_status('Invalid filename selected', WARNING)

    def export_to_csv(self, csv_path):
        query = QSqlQuery("SELECT * FROM tools")
        if not query.isActive():
            return False
        record = query.record()
        headers = [record.fieldName(i) for i in range(record.count())]

        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            while query.next():
                row_csv = [query.value(i) for i in range(record.count())]
                writer.writerow(row_csv)
        return True

    def export_to_html(self, html_path):
        query = QSqlQuery("SELECT * FROM tools")
        if not query.isActive():
            return False
        record = query.record()
        html_content = []
        headers = []
        hdr = []
        for i in range(record.count()):
            hdr.append(record.fieldName(i))
        hdr[2] = 'GROUP'
        for i in range(record.count()):
            headers.append(f"<th>{hdr[i]}</th>")
        html_content.append("<html><head><meta charset='UTF-8'></head><body>")
        html_content.append("<table border='1' cellspacing='0' cellpadding='5'>")
        html_content.append("<tr>" + "".join(headers) + "</tr>")
        while query.next():
            row = []
            row_html = []
            for i in range(record.count()):
                row.append(query.value(i))
            idx = int(row[2])
            row[2] = self.agent.group_items[idx].text(0)
            for i in range(record.count()):
                row_html.append(f"<td>{row[i]}</td>")
            html_content.append("<tr>" + ''.join(row_html) + "</tr>")
        html_content.append("</table></body></html>")
       
        with open(html_path, 'w', encoding='utf-8') as f:
            for line in html_content:
                f.write(line + '\n')
        self.parent.add_status(f'Exported Tools to {html_path}')
        return True

## helper functions
    def show_groupMenu(self, pos):
        current_item = self.treeWidget.currentItem()
        if not current_item.data(0, grpRole): return
        group_name = current_item.text(0)
        menu = QMenu()
        remove_action = menu.addAction(f"Remove group {group_name}")
        action = menu.exec_(self.cmb_group.mapToGlobal(pos))
        if action == remove_action:
            index = self.cmb_group.currentIndex()
            if self.agent.remove_tree_item(current_item):
                self.cmb_group.removeItem(index)
                self.parent.add_status(f'Removed group {group_name} from database')
            else:
                self.parent.add_status(f'Cannot remove {group_name} until all tools have been moved out', WARNING)

    def show_materialMenu(self, pos):
        current_item = self.treeWidget.currentItem()
        tool_no = current_item.data(0, tnoRole)
        material_id = current_item.data(0, midRole)
        material = self.cmb_material.currentText()
        if material == 'None': return
        if tool_no is not None:
            tool = current_item.data(0, tnoRole)
        elif material_id:
            tool = current_item.parent().data(0, tnoRole)
        menu = QMenu()
        add_action = menu.addAction(f"Add {material} to tool {tool}")
        remove_action = menu.addAction(f"Remove {material} from tool {tool}")
        remove_all_action = menu.addAction(f"Remove {material} from database")
        action = menu.exec_(self.cmb_material.mapToGlobal(pos))

        if tool_no and action == add_action:
            for i in range(current_item.childCount()):
                if current_item.child(i).text(0) == material:
                    self.parent.add_status(f'{material} already exists in tool {tool_no}', WARNING)
                    return
            new_id = self.agent.get_material_id(material)
            new_item = self.agent.create_material_item(current_item, material, new_id)
            self.agent.update_material_data((0, 0, 0, 0), tool_no, new_id)
            self.parent.add_status(f'Added {material} to tool {tool}')

        elif tool_no and action == remove_action:
            for i in range(current_item.childCount()):
                item = current_item.child(i)
                if item.text(0) == material:
                    if self.agent.remove_tree_item(item, tool_no):
                        self.parent.add_status(f'Removed {material} from tool {tool_no}')
                    break

        elif material_id and action == remove_action:
            if current_item.text(0) == material:
                if self.agent.remove_tree_item(current_item, tool):
                    self.parent.add_status(f'Removed {material} from tool {tool}')

        elif action == remove_all_action:
            used = False
            for item in self.agent.tool_items.values():
                for i in range(item.childCount()):
                    if  item.child(i).text(0) == material:
                        used = True
                        self.parent.add_status(f'{material} is being used by other tools', WARNING)
                        break
                if used is True: break
            if not used:
                self.agent.remove_material(material)
                idx = self.cmb_material.currentIndex()
                self.cmb_material.removeItem(idx)
                self.parent.add_status(f'{material} removed from database')

    def clear_parm_lines(self):
        self.lineEdit_rpm.setText('0')
        self.lineEdit_feedrate.setText('0.0')
        self.lineEdit_stepover.setText('0.0')
        self.lineEdit_depth.setText('0.0')

    def expand_all(self, state):
        if state:
            self.treeWidget.expandAll()

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
        self.module = Tool_Database(self)
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
