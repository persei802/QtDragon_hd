#!/usr/bin/env python3
# Copyright (c) 2026 Jim Sloot (persei802@gmail.com)
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
import re
import importlib

from qtpy import uic
from qtpy.QtGui  import QFont
from qtpy.QtCore import QObject, Qt, QUrl, QSettings
from qtpy.QtWidgets import (QWidget, QDialog, QDialogButtonBox, QVBoxLayout, QTabWidget, 
                            QPlainTextEdit, QListWidgetItem)
from qtpy.QtWebEngineWidgets import QWebEngineView
from qtpy.QtWebEngineWidgets import QWebEnginePage

from qtvcp.core import Info, Path
from qtvcp.lib.qt_pdf import PDFViewer
from qtvcp import logger

LOG = logger.getLogger(__name__)
LOG.setLevel(logger.INFO) # One of DEBUG, INFO, WARNING, ERROR, CRITICAL
INFO = Info()
PATH = Path()
HERE = os.path.dirname(os.path.abspath(__file__))

# status message alert levels
DEFAULT =  0
WARNING =  1
ERROR = 2

# this class provides an overloaded function to disable navigation links
class WebPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, navtype, mainframe):
        if navtype == self.NavigationTypeLinkClicked: return False
        return super().acceptNavigationRequest(url, navtype, mainframe)


# utilities that have a Help page, use this to display the page
class ShowHelp(QDialog):
    def __init__(self):
        super(ShowHelp, self).__init__()
        layout = QVBoxLayout()
        self.webview = QWebEngineView()
        self.webpage = QWebEnginePage()
        self.webview.setPage(self.webpage)
        self.setWindowTitle('QtDragon Help')
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        bbox = QDialogButtonBox()
        bbox.addButton(QDialogButtonBox.Ok)
        layout.addWidget(self.webview)
        layout.addWidget(bbox)
        self.setLayout(layout)
        self.hide()

        bbox.accepted.connect(self.accept)

    def load_page(self, fname):
        url = QUrl("file:///" + fname)
        self.webpage.load(url)
        self.show()


class Plugin_Manager(QWidget):
    def __init__(self, parent=None):
        super(Plugin_Manager, self).__init__()
        self.parent = parent
        self.w = parent.w
        self.settings = QSettings('qtdragon', 'plugins')
        # Load the widgets UI file:
        self.filename = os.path.join(HERE, 'plugin_manager.ui')
        try:
            self.instance = uic.loadUi(self.filename, self)
        except AttributeError as e:
            self.parent.add_status(e, WARNING)
        self.listWidget_plugins.itemPressed.connect(self.itemPressed)

    def add_items(self, items):
        for item in items.keys():
            new_item = QListWidgetItem(item)
            new_item.setFlags(new_item.flags() | Qt.ItemIsUserCheckable)
            enabled = self.settings.value(f'plugins/{item}', False, bool)
            state = Qt.Checked if enabled else Qt.Unchecked
            new_item.setCheckState(state)
            data = {'name': None,
                    'version': None,
                    'status': 'Not Installed',
                    'description': None}
            new_item.setData(Qt.UserRole, data)
            new_item.setText(item)
            self.listWidget_plugins.addItem(new_item)

    def add_info(self, plugin, info):
        items = self.listWidget_plugins.findItems(plugin, Qt.MatchExactly)
        if items:
            item = items[0]
            data = item.data(Qt.UserRole)
            data['name'] = info['mod_name']
            data['version'] = info['version']
            data['description'] = info['description']
            item.setData(Qt.UserRole, data)

    def get_status(self, plugin):
        return self.settings.value(f'plugins/{plugin}', False, bool)

    def change_status(self, plugin, status):
        items = self.listWidget_plugins.findItems(plugin, Qt.MatchExactly)
        if items:
            item = items[0]
            data = item.data(Qt.UserRole)
            data['status'] = status
            item.setData(Qt.UserRole, data)

    def itemPressed(self, item):
        data = item.data(Qt.UserRole)
        self.lbl_name.setText(data['name'])
        self.lbl_version.setText(data['version'])
        self.lbl_status.setText(data['status'])
        self.lbl_description.setText(data['description'])

    def closing_cleanup__(self):
        for i in range(self.listWidget_plugins.count()):
            item = self.listWidget_plugins.item(i)
            self.settings.setValue(f'plugins/{item.text()}', item.checkState() == Qt.Checked)
        self.settings.sync()

class Setup_Utils():
    def __init__(self, parent):
        self.w = parent.w
        self.parent = parent
        self.installed_modules = list()
        self.doc_index = 0
        self.util_list = []
        self.help = ShowHelp()
        # install plugin manager to handler UI
        self.plugins = Plugin_Manager(self.parent)
        self.w.stackedWidget_utils.addWidget(self.plugins)
        self.util_list.append('PLUGIN MANAGER')
        self.installed_modules.append(self.plugins)

        plugins = self.get_plugin_list()
        self.init_utils(plugins)

    def closing_cleanup__(self):
        for mod in self.installed_modules:
            if 'closing_cleanup__' in dir(mod):
                mod.closing_cleanup__()

    def get_plugin_list(self):
        # get list of all python files in plugins folder
        path = os.path.join(PATH.CONFIGPATH, "plugins")
        modules = []
        pfiles = os.listdir(path)
        pfiles.sort()
        for item in pfiles:
            if item.endswith(".py"):
                name, ext = os.path.splitext(item)
                modules.append(name)
        # sort out any files that don't have PLUGIN_INFO
        plugins = {}
        for item in modules:
            module = importlib.import_module(f"plugins.{item}")
            try:
                plugins[item] = module.PLUGIN_INFO
            except:
                pass
        return plugins

    def init_utils(self, plugins):
        # populate module names in listWidget
        self.plugins.add_items(plugins)
        for plugin in plugins.keys():
            status = self.plugins.get_status(plugin)
            if status is False: continue
            module = importlib.import_module(f"plugins.{plugin}")
            info = plugins[plugin]
            self.plugins.add_info(plugin, info)
            mod_name = info['mod_name']
            class_name = info['class_name']
            item_text = info['item_text']
            self.install_module(mod_name, class_name, item_text)
            self.plugins.change_status(plugin, 'Installed')
       # install permanent utilities
        self.install_document_viewer()
        self.show_defaults()

    def install_module(self, mod_name, class_name, item):
        mod_path = 'plugins.' + mod_name
        try:
            module = importlib.import_module(mod_path)
            cls = getattr(module, class_name)
            self[mod_name] = cls(self)
            self.installed_modules.append(self[mod_name])
        except FileNotFoundError:
            print(f'File {mod_name} not found')
            return
        except SyntaxError as e:
            print(f'Syntax error in {mod_name}: {e}')
            return
        except ImportError as e:
            print(f'Import error: {e}')
            return
        self.w.stackedWidget_utils.addWidget(self[mod_name])
        self.util_list.append(item)
        # some plugins may not have a _hal_init method
        try:
            self[mod_name]._hal_init()
        except: pass
        LOG.debug(f"Installed utility: {class_name}")

    def install_document_viewer(self):
        self.doc_viewer = QTabWidget()
        self.doc_index = self.w.stackedWidget_utils.addWidget(self.doc_viewer)
        self.util_list.append('DOCUMENT VIEWER')
        # html page viewer
        self.web_view_setup = QWebEngineView()
        self.web_page_setup = WebPage()
        self.web_view_setup.setPage(self.web_page_setup)
        self.doc_viewer.addTab(self.web_view_setup, 'HTML')
        # PDF page viewer
        self.PDFView = PDFViewer.PDFView()
        self.doc_viewer.addTab(self.PDFView, 'PDF')
        # text page viewer
        self.text_view = QPlainTextEdit()
        self.text_view.setReadOnly(True)
        self.doc_viewer.addTab(self.text_view, 'TEXT')
        # gcode properties viewer
        self.gcode_properties = QPlainTextEdit()
        self.gcode_properties.setReadOnly(True)
        # need a monospace font or text won't line up
        self.gcode_properties.setFont(QFont("Courier", 12))
        self.doc_viewer.addTab(self.gcode_properties, 'GCODE')
        LOG.debug("Installed utility: Document Viewer")

    def show_defaults(self):
        # default html page
        try:
            fname = os.path.join(PATH.CONFIGPATH, 'qtdragon/default_setup.html')
            url = QUrl("file:///" + fname)
            self.web_page_setup.load(url)
        except Exception as e:
            self.parent.add_status(f"Could not find default HTML file - {e}", ERROR)
        # default pdf file
        try:
            fname = os.path.join(PATH.CONFIGPATH, 'qtdragon/default_setup.pdf')
            self.PDFView.loadView(fname)
        except Exception as e:
            self.parent.add_status(f"Could not find default PDF file - {e}", ERROR)

# Calls from external modules
    def show_html(self, fname):
        url = QUrl("file:///" + fname)
        self.web_page_setup.load(url)
        self.w.stackedWidget_utils.setCurrentIndex(self.doc_index)
        self.doc_viewer.setCurrentIndex(0)

    def show_pdf(self, fname):
        self.PDFView.loadView(fname)
        self.w.stackedWidget_utils.setCurrentIndex(self.doc_index)
        self.doc_viewer.setCurrentIndex(1)

    def show_text(self, fname):
        with open(fname, 'r') as lines:
            text = lines.read()
            self.text_view.setPlainText(text)
        self.w.stackedWidget_utils.setCurrentIndex(self.doc_index)
        self.doc_viewer.setCurrentIndex(2)

    def show_gcode_properties(self, props):
        lines = props.split('\n')
        # convert huge numbers to scientific notation
        for index, line in enumerate(lines):
            numbers = re.findall(r'-?\d+\.?\d*', line)
            for num in numbers:
                value = float(num)
                if abs(value) > 100000:
                    data = f'{value:.3e}'
                    line = line.replace(num, data)
            lines[index] = line
        # arrange lines into 2 columns
        col_width = 30
        for index, line in enumerate(lines):
            parts = line.split(':')
            if len(parts) < 2: continue
            key = parts[0] + ':'
            while len(key) < col_width:
                key += ' '
            line = key + parts[1]
            lines[index] = line
        text = "\n".join(lines)
        self.gcode_properties.setPlainText(text)
        self.doc_viewer.setCurrentIndex(3)

    def get_util_list(self):
        return self.util_list

    def show_help(self, fname):
        self.help.load_page(fname)

    # pass status message from utility to handler
    def add_status(self, msg, level=None):
        self.parent.add_status(msg, level)

    # required code for subscriptable objects
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)
