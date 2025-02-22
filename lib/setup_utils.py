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
import xml.etree.ElementTree as ET

from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtWidgets import QPushButton, QStackedWidget, QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout, QSizePolicy
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
HELP = os.path.join(PATH.CONFIGPATH, "help_files")

# status message alert levels
DEFAULT =  0
WARNING =  1
CRITICAL = 2

# this class provides an overloaded function to disable navigation links
class WebPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, navtype, mainframe):
        if navtype == self.NavigationTypeLinkClicked: return False
        return super().acceptNavigationRequest(url, navtype, mainframe)


class ShowHelp(QtCore.QObject):
    def __init__(self, dialog):
        super(ShowHelp, self).__init__()
        layout = QVBoxLayout(dialog)
        dialog.setWindowTitle('Utility Help')
        dialog.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint)
        self.webview = QWebEngineView()
        bbox = QDialogButtonBox()
        bbox.addButton(QDialogButtonBox.Ok)
        layout.addWidget(self.webview)
        layout.addWidget(bbox)

        bbox.accepted.connect(dialog.accept)

    def load_url(self, url):
        self.webview.load(url)

class SetupAbout():
    def __init__(self, widgets, parent):
        self.w = widgets
        self.parent = parent
        self.about_btns = {'ABOUT': 'intro',
                           'USING A VFD': 'vfd',
                           'SPINDLE PAUSE': 'spindle_pause',
                           'USING A MPG': 'mpg',
                           'TOOL TOUCHOFF': 'touchoff',
                           'RUN FROM LINE': 'runfromline',
                           'STYLESHEETS': 'stylesheets',
                           'ROTARY AXIS': 'rotary_axis',
                           'CUSTOM PANELS': 'custom'}

        self.web_view_about = QWebEngineView()
        self.web_page_about = WebPage()
        self.web_view_about.setPage(self.web_page_about)
        self.w.layout_about_pages.addWidget(self.web_view_about)

        self.show_defaults()

    def show_about_page(self, page):
        fname = os.path.join(HELP, 'about_' + page + '.html')
        if os.path.dirname(fname):
            url = QtCore.QUrl("file:///" + fname)
            self.web_page_about.load(url)
        else:
            self.parent.add_status(f"About file {fname} not found")

    def show_defaults(self):
        try:
            fname = os.path.join(HELP, 'about_intro.html')
            url = QtCore.QUrl("file:///" + fname)
            self.web_page_about.load(url)
        except Exception as e:
            self.parent.add_status(f"Could not find default ABOUT page - {e}", CRITICAL)

    def get_about_dict(self):
        return self.about_btns


class SetupUtils():
    def __init__(self, widgets, parent):
        self.w = widgets
        self.parent = parent
        self.tool_db = self.parent.tool_db
        self.doc_index = 0
        self.utils_dict = {}
        self.btn_idx = 0
        # setup XML parser
        xml_filename = os.path.join(HERE, 'utils.xml')
        self.tree = ET.parse(xml_filename)
        self.root = self.tree.getroot()
        self.machine = self.root.get('type')
        # setup help file viewer
        self.dialog = QDialog()
        self.help_page = ShowHelp(self.dialog)
        self.dialog.hide()

    def init_utils(self):
        xml = self.root.find('Utils')
        for child in xml:
            install = child.get('install')
            if install == 'yes':
                cmd = 'install_' + child.tag
                if cmd in dir(self):
                    self[cmd]()
                    LOG.debug(f"Installed {child.tag} utility")
                else:
                    LOG.debug(f"No such utility as {child.tag}")

        self.show_defaults()

    def install_facing(self):
        from lib.facing import Facing
        self.facing = Facing(self.tool_db, self.parent, self)
        self.w.stackedWidget_utils.addWidget(self.facing)
        self.utils_dict['FACING'] = self.btn_idx
        self.btn_idx += 1
        self.facing._hal_init()

    def install_hole_circle(self):
        from lib.hole_circle import Hole_Circle
        self.hole_circle = Hole_Circle(self.parent, self)
        self.w.stackedWidget_utils.addWidget(self.hole_circle)
        self.utils_dict['HOLE CIRCLE'] = self.btn_idx
        self.btn_idx += 1
        self.hole_circle._hal_init()

    def install_auto_measure(self):
        from lib.auto_height import Auto_Measure
        self.auto_measure = Auto_Measure(self.w, self.parent, self)
        self.w.stackedWidget_utils.addWidget(self.auto_measure)
        self.utils_dict['WORKPIECE HEIGHT'] = self.btn_idx
        self.btn_idx += 1
        self.auto_measure._hal_init()

    def install_zlevel(self):
        from lib.zlevel import ZLevel
        self.zlevel = ZLevel(self.w, self.parent, self)
        self.parent.zlevel = self.zlevel
        self.w.stackedWidget_utils.addWidget(self.zlevel)
        self.utils_dict['Z LEVEL COMP'] = self.btn_idx
        self.btn_idx += 1
        self.zlevel._hal_init()

    def install_spindle_warmup(self):
        from lib.spindle_warmup import Spindle_Warmup
        self.warmup = Spindle_Warmup(self.parent)
        self.w.stackedWidget_utils.addWidget(self.warmup)
        self.utils_dict['SPINDLE WARMUP'] = self.btn_idx
        self.btn_idx += 1
        self.warmup._hal_init()

    def install_hole_enlarge(self):
        from lib.hole_enlarge import Hole_Enlarge
        self.enlarge = Hole_Enlarge(self.tool_db, self.parent, self)
        self.w.stackedWidget_utils.addWidget(self.enlarge)
        self.utils_dict['HOLE ENLARGE'] = self.btn_idx
        self.btn_idx += 1
        self.enlarge._hal_init()

    def install_ngcgui(self):
        LOG.info("Using NGCGUI utility")
        from lib.ngcgui import NgcGui
        self.ngcgui = NgcGui()
        self.w.stackedWidget_utils.addWidget(self.ngcgui)
        self.utils_dict['NGCGUI'] = self.btn_idx
        self.btn_idx += 1
        self.ngcgui._hal_init()

    def install_gcodes(self):
        from lib.gcodes import GCodes
        self.gcodes = GCodes(self)
        self.w.stackedWidget_utils.addWidget(self.gcodes)
        self.utils_dict['GCODES'] = self.btn_idx
        self.btn_idx += 1
        self.gcodes.setup_list()

    def install_rapid_rotary(self):
        if 'A' in INFO.AVAILABLE_AXES:
            from lib.rapid_rotary import Rapid_Rotary
            self.rapid_rotary = Rapid_Rotary(self)
            self.w.stackedWidget_utils.addWidget(self.rapid_rotary)
            self.utils_dict['RAPID ROTARY'] = self.btn_idx
            self.btn_idx += 1
            self.rapid_rotary._hal_init()

    def install_document_viewer(self):
        self.doc_viewer = QtWidgets.QTabWidget()
        self.doc_index = self.w.stackedWidget_utils.addWidget(self.doc_viewer)
        self.utils_dict['DOCUMENT VIEWER'] = self.btn_idx
        self.btn_idx += 1
        # html page viewer
        self.web_view_setup = QWebEngineView()
        self.web_page_setup = WebPage()
        self.web_view_setup.setPage(self.web_page_setup)
        self.doc_viewer.addTab(self.web_view_setup, 'HTML')
        # PDF page viewer
        self.PDFView = PDFViewer.PDFView()
        self.doc_viewer.addTab(self.PDFView, 'PDF')
        # gcode properties viewer
        self.gcode_properties = QtWidgets.QPlainTextEdit()
        self.gcode_properties.setReadOnly(True)
        # need a monospace font or text won't line up
        self.gcode_properties.setFont(QtGui.QFont("Courier", 12))
        self.doc_viewer.addTab(self.gcode_properties, 'GCODE')

    def get_utils_dict(self):
        return self.utils_dict

    def show_defaults(self):
        # default html page
        try:
            fname = os.path.join(PATH.CONFIGPATH, 'qtdragon/default_setup.html')
            url = QtCore.QUrl("file:///" + fname)
            self.web_page_setup.load(url)
        except Exception as e:
            self.parent.add_status(f"Could not find default HTML file - {e}", CRITICAL)
        # default pdf file
        try:
            fname = os.path.join(PATH.CONFIGPATH, 'qtdragon/default_setup.pdf')
            self.PDFView.loadView(fname)
        except Exception as e:
            self.parent.add_status(f"Could not find default PDF file - {e}", CRITICAL)

    def show_html(self, fname):
        url = QtCore.QUrl("file:///" + fname)
        self.web_page_setup.load(url)
        self.w.stackedWidget_utils.setCurrentIndex(self.doc_index)
        self.doc_viewer.setCurrentIndex(0)

    def show_pdf(self, fname):
        self.PDFView.loadView(fname)
        self.w.stackedWidget_utils.setCurrentIndex(self.doc_index)
        self.doc_viewer.setCurrentIndex(1)

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
        self.doc_viewer.setCurrentIndex(2)

    def show_help_page(self, page):
        url = QtCore.QUrl("file:///" + page)
        self.help_page.load_url(url)
        self.dialog.show()

    # required code for subscriptable objects
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    w = SetupUtils()
    w.show()
    sys.exit( app.exec_() )

