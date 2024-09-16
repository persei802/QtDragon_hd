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
import xml.etree.ElementTree as ET

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtWidgets import QPushButton, QStackedWidget, QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout, QSizePolicy
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebEngineWidgets import QWebEnginePage

from qtvcp.core import Info, Path
from qtvcp.widgets.screen_options import ScreenOptions
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
        self.tool_db = self.parent.tool_db
        self.html_setup_index = 0
        self.pdf_setup_index = 0
        self.util_btns = []
        self.num_utils = 0
        self.max_util_btns = 8
        self.btn_idx = 0
        self.scroll_window = {'left': 0, 'right': 0}
        self.sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.stackedWidget_utils = QStackedWidget()
        self.stackedWidget_utils.setSizePolicy(self.sizePolicy)
        self.w.layout_utils.addWidget(self.stackedWidget_utils)
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
        # html setup page viewer
        self.web_view_setup = QWebEngineView()
        self.web_page_setup = WebPage()
        self.web_view_setup.setPage(self.web_page_setup)
        self.html_setup_index = self.stackedWidget_utils.addWidget(self.web_view_setup)
        self.make_button('html', 'HTML\nVIEWER')
        # PDF setup page viewer
        self.PDFView = PDFViewer.PDFView()
        self.pdf_setup_index = self.stackedWidget_utils.addWidget(self.PDFView)
        self.make_button('pdf', 'PDF\nVIEWER')

        self.num_utils = len(self.util_btns)
        self['btn_' + self.util_btns[0]].setChecked(True)
        self.scroll_window['left'] = 0
        self.scroll_window['right'] = self.max_util_btns - 1

        if self.num_utils <= self.max_util_btns:
            self.w.btn_util_left.hide()
            self.w.btn_util_right.hide()
        else:
            self.slide_scroll_window()
        self.w.util_buttonGroup.buttonClicked.connect(self.utils_tab_changed)
        self.show_defaults()

    def install_facing(self):
        from lib.facing import Facing
        self.facing = Facing(self.tool_db, self.parent, self)
        self.stackedWidget_utils.addWidget(self.facing)
        self.make_button('facing', 'FACING')
        self.facing._hal_init()

    def install_hole_circle(self):
        from lib.hole_circle import Hole_Circle
        self.hole_circle = Hole_Circle(self.parent, self)
        self.stackedWidget_utils.addWidget(self.hole_circle)
        self.make_button('hole_circle', 'HOLE\nCIRCLE')
        self.hole_circle._hal_init()

    def install_auto_measure(self):
        from lib.auto_height import Auto_Measure
        self.auto_measure = Auto_Measure(self.w, self.parent, self)
        self.stackedWidget_utils.addWidget(self.auto_measure)
        self.make_button('auto_measure', 'WORKPIECE\nHEIGHT')
        self.auto_measure._hal_init()

    def install_zlevel(self):
        from lib.zlevel import ZLevel
        self.zlevel = ZLevel(self.w, self.parent, self)
        self.parent.zlevel = self.zlevel
        self.stackedWidget_utils.addWidget(self.zlevel)
        self.make_button('zlevel', 'Z LEVEL\nCOMP')
        self.zlevel._hal_init()

    def install_spindle_warmup(self):
        from lib.spindle_warmup import Spindle_Warmup
        self.warmup = Spindle_Warmup(self.parent)
        self.stackedWidget_utils.addWidget(self.warmup)
        self.make_button('warmup', 'SPINDLE\nWARMUP')
        self.warmup._hal_init()

    def install_hole_enlarge(self):
        from lib.hole_enlarge import Hole_Enlarge
        self.enlarge = Hole_Enlarge(self.tool_db, self.parent, self)
        self.stackedWidget_utils.addWidget(self.enlarge)
        self.make_button('enlarge', 'HOLE\nENLARGE')
        self.enlarge._hal_init()

    def install_ngcgui(self):
        LOG.info("Using NGCGUI utility")
        from lib.ngcgui import NgcGui
        self.ngcgui = NgcGui()
        self.stackedWidget_utils.addWidget(self.ngcgui)
        self.make_button('ngcgui', 'NGCGUI')
        self.ngcgui._hal_init()

    def install_gcodes(self):
        from lib.gcodes import GCodes
        self.gcodes = GCodes(self)
        self.stackedWidget_utils.addWidget(self.gcodes)
        self.make_button('gcodes', 'GCODES')
        self.gcodes.setup_list()

    def install_rapid_rotary(self):
        if 'A' in INFO.AVAILABLE_AXES:
            from lib.rapid_rotary import Rapid_Rotary
            self.rapid_rotary = Rapid_Rotary(self)
            self.stackedWidget_utils.addWidget(self.rapid_rotary)
            self.make_button('rotary', 'RAPID\nROTARY')
            self.rapid_rotary._hal_init()

    def make_button(self, name, title):
        self['btn_' + name] = QPushButton(title)
        self['btn_' + name].setSizePolicy(self.sizePolicy)
        self['btn_' + name].setMinimumSize(QtCore.QSize(90, 0))
        self['btn_' + name].setCheckable(True)
        self['btn_' + name].setProperty('index', self.btn_idx)
        self.w.util_buttonGroup.addButton(self['btn_' + name])
        self.w.layout_util_btns.insertWidget(self.btn_idx + 1, self['btn_' + name])
        self.util_btns.append(name)
        self.btn_idx += 1

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
        self.stackedWidget_utils.setCurrentIndex(self.html_setup_index)
        self.btn_html.setChecked(True)

    def show_pdf(self, fname):
        self.PDFView.loadView(fname)
        self.stackedWidget_utils.setCurrentIndex(self.pdf_setup_index)
        self.btn_pdf.setChecked(True)

    def show_help_page(self, page):
        url = QtCore.QUrl("file:///" + page)
        self.help_page.load_url(url)
        self.dialog.show()

    def utils_tab_changed(self, btn):
        if btn == self.w.btn_util_left:
            self.scroll_left()
        elif btn == self.w.btn_util_right:
            self.scroll_right()
        else:
            index = btn.property('index')
            self.stackedWidget_utils.setCurrentIndex(index)

    def scroll_left(self):
        if self.scroll_window['left'] > 0:
            self.scroll_window['left'] -= 1
            self.scroll_window['right'] -= 1
            self.slide_scroll_window()

    def scroll_right(self):
        if self.scroll_window['right'] < self.num_utils - 1:
            self.scroll_window['left'] += 1
            self.scroll_window['right'] += 1
            self.slide_scroll_window()

    def slide_scroll_window(self):
        for item in self.util_btns:
            index = self['btn_' + item].property('index')
            if index < self.scroll_window['left'] or index > self.scroll_window['right']:
                self['btn_' + item].hide()
            else:
                self['btn_' + item].show()

    # required code for subscriptable objects
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    w = Setup_Utils()
    w.show()
    sys.exit( app.exec_() )

