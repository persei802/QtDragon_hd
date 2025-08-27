#!/usr/bin/env python3
# Copyright (c) 2023 Jim Sloot (persei802@gmail.com)
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
import xml.etree.ElementTree as ET

from PyQt5.QtGui  import QFont
from PyQt5.QtCore import QObject, Qt, QUrl
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QTabWidget, QPlainTextEdit
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebEngineWidgets import QWebEnginePage

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


class ShowHelp(QObject):
    def __init__(self, dialog):
        super(ShowHelp, self).__init__()
        layout = QVBoxLayout(dialog)
        dialog.setWindowTitle('Utility Help')
        dialog.setWindowFlags(Qt.WindowStaysOnTopHint)
        self.webview = QWebEngineView()
        bbox = QDialogButtonBox()
        bbox.addButton(QDialogButtonBox.Ok)
        layout.addWidget(self.webview)
        layout.addWidget(bbox)

        bbox.accepted.connect(dialog.accept)

    def load_url(self, url):
        self.webview.load(url)

class Setup_Utils():
    def __init__(self, widgets, parent):
        self.w = widgets
        self.parent = parent
        if self.parent is not None:
            self.tool_db = self.parent.tool_db
        self.installed_modules = list()
        self.zlevel = None
        self.doc_index = 0
        self.util_list = []
        # setup XML parser
        xml_filename = os.path.join(HERE, 'utils.xml')
        self.tree = ET.parse(xml_filename)
        self.root = self.tree.getroot()
        # setup help file viewer
        self.dialog = QDialog()
        self.help_page = ShowHelp(self.dialog)
        self.dialog.hide()

    def closing_cleanup__(self):
        for mod in self.installed_modules:
            if 'closing_cleanup__' in dir(mod):
                mod.closing_cleanup__()

    def init_utils(self):
        # install optional utilities
        utils = self.root.findall("util")
        for util in utils:
            mod_name = util.find("module").text
            class_name = util.find("class").text 
            item_text = util.find("name").text
            self.install_module(mod_name, class_name, item_text)
        # check if Z level compensation was installed
        if self.zlevel is not None:
            self.parent.zlevel = self.zlevel
        # install permanent utilities
        self.install_rapid_rotary()
        self.install_document_viewer()
        self.install_gcodes()
        self.show_defaults()

    def install_module(self, mod_name, class_name, item):
        mod_path = 'utils.' + mod_name
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
        self[mod_name]._hal_init()
        LOG.debug(f"Installed utility: {class_name}")

    def install_gcodes(self):
        from utils.gcodes import GCodes
        self.gcodes = GCodes()
        self.w.stackedWidget_utils.addWidget(self.gcodes)
        self.util_list.append('GCODES')
        self.gcodes.setup_list()
        LOG.debug("Installed utility: GCodes")

    def install_rapid_rotary(self):
        if 'A' in INFO.AVAILABLE_AXES:
            from utils.rapid_rotary import Rapid_Rotary
            self.rapid_rotary = Rapid_Rotary(self)
            self.w.stackedWidget_utils.addWidget(self.rapid_rotary)
            self.util_list.append('RAPID ROTARY')
            self.rapid_rotary._hal_init()
            LOG.debug("Installed utility: Rapid Rotary")

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

    def show_help_page(self, page):
        url = QUrl("file:///" + page)
        self.help_page.load_url(url)
        self.dialog.show()

    def get_util_list(self):
        return self.util_list

    # required code for subscriptable objects
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)

if __name__ == "__main__":
    app = PyqQt5.QtWidgets.QApplication(sys.argv)
    w = Setup_Utils(None, None)
    w.init_utils()
    sys.exit( app.exec_() )

