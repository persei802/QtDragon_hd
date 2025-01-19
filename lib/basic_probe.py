#!/usr/bin/env python3
# Qtvcp basic probe
#
# Copyright (c) 2020  Chris Morley <chrisinnanaimo@hotmail.com>
# Copyright (c) 2020  Jim Sloot <persei802@gmail.com>
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
#
# a probe screen based on ProbeBasic screen

import sys
import os
import json
from PyQt5.QtCore import QProcess, QEvent, QObject, QRegularExpression, QFile, Qt, pyqtSignal
from PyQt5 import QtGui, QtWidgets, uic
from qtvcp.widgets.widget_baseclass import _HalWidgetBase
from qtvcp.core import Action, Status, Info, Path, Tool
from qtvcp.widgets.calculator import Calculator
from qtvcp import logger

ACTION = Action()
STATUS = Status()
INFO = Info()
TOOL = Tool()
PATH = Path()
HERE = os.path.dirname(os.path.abspath(__file__))
LOG = logger.getLogger(__name__)
LOG.setLevel(logger.INFO) # One of DEBUG, INFO, WARNING, ERROR, CRITICAL

current_dir =  os.path.dirname(__file__)
SUBPROGRAM = os.path.abspath(os.path.join(current_dir, 'probe_subprog.py'))
CONFIG_DIR = os.getcwd()
HELP = os.path.join(PATH.CONFIGPATH, "help_files")

# StatusBar message alert levels
DEFAULT =  0
WARNING =  1
ERROR = 2

class EventFilter(QObject):
    def __init__(self, widgets):
        super().__init__()
        self.w = widgets
        self.use_calc = False
        self.line_list = []
        self._nextIndex = 0
        self.hilightStyle = "border: 1px solid cyan;"
        self._oldStyle = ''
        self.calc = CalcInput()

        self.tmpl = '.3f' if INFO.MACHINE_IS_METRIC else '.4f'

        self.calc.apply_action.connect(lambda: self.calc_data(apply=True))
        self.calc.next_action.connect(lambda: self.calc_data(next=True))
        self.calc.back_action.connect(lambda: self.calc_data(back=True))
        self.calc.accepted.connect(lambda: self.calc_data(accept=True))
        self.calc.rejected.connect(self.calc_data)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.FocusIn:
            if isinstance(obj, QtWidgets.QLineEdit) and self.use_calc:
                # only if mouse selected
                if event.reason() == 0:
                    self._nextIndex = self.line_list.index(obj.objectName().replace('lineEdit_',''))
                    self.popEntry(obj)
                    obj.clearFocus()
                    event.accept()
                    return True
        return False

    def popEntry(self, obj, next=False):
        obj.setStyleSheet(self.hilightStyle)
        self.calc.setWindowTitle(f"Enter data for {obj.objectName().replace('lineEdit_','')}")
        preset = obj.text()
        if preset == '': preset = '0'
        self.calc.display.setText(preset)
        if not next:
            self.calc.show()

    def calc_data(self, next=False, back=False, apply=False, accept=False):
        line = self.line_list[self._nextIndex]
        self.w[f'lineEdit_{line}'].setStyleSheet(self._oldStyle)
        if next:
            self._nextIndex += 1
            if self._nextIndex == len(self.line_list):
                self._nextIndex = 0
        elif back:
            self._nextIndex -= 1
            if self._nextIndex < 0:
                self._nextIndex = len(self.line_list) - 1
        elif apply or accept:
            text = self.calc.display.text()
            if line == 'probe_tool':
                value = float(text)
                value = int(value)
                self.w.lineEdit_probe_tool.setText(str(value))
            else:
                value = float(text)
                self.w[f'lineEdit_{line}'].setText(f'{value:{self.tmpl}}')
            if apply:
                self._nextIndex += 1
                if self._nextIndex == len(self.line_list):
                    self._nextIndex = 0
        if next or back or apply:
            newobj = self.w[f'lineEdit_{self.line_list[self._nextIndex]}']
            self.popEntry(newobj, True)

    def set_calc_mode(self, mode):
        self.use_calc = mode

    def set_line_list(self, data):
        self.line_list = data

    def set_old_style(self, style):
        self._oldStyle = style

    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)


class BasicProbe(QtWidgets.QWidget, _HalWidgetBase):
    def __init__(self, parent=None):
        super(BasicProbe, self).__init__()
        self.parent = parent
        self.regex = ''
        try:
            self.tool_db = self.parent.tool_db
        except Exception as e:
            print(e)
            self.tool_db = None
        self.proc = None
        self.test_mode = False
        self.help = HelpPage()
        self.probe_settings = []
        self.setMinimumSize(600, 420)
        # load the widgets ui file
        self.filename = os.path.join(HERE, 'basic_probe.ui')
        try:
            self.instance = uic.loadUi(self.filename, self)
        except AttributeError as e:
            LOG.critical(e)

        self.probe_page_list = ['OUTSIDE MEASUREMENTS',
                                'INSIDE MEASUREMENTS',
                                'ANGLE MEASUREMENTS',
                                'BOSS AND POCKET',
                                'RIDGE AND VALLEY',
                                'CALIBRATION']

        # populate probe page combobox
        self.cmb_probe_select.clear()
        self.cmb_probe_select.addItems(self.probe_page_list)
        self.cmb_probe_select.wheelEvent = lambda event: None

        self.status_list = ['xm', 'xc', 'xp', 'ym', 'yc', 'yp', 'lx', 'ly', 'z', 'd', 'a', 'delta']

        #create parameter dictionary
        self.send_dict = {}
        # these parameters are sent to the subprogram
        # this is also the order of the next widget when calculator 'next' button is pressed
        self.parm_list = ['probe_diam',
                          'rapid_vel',
                          'search_vel',
                          'probe_vel',
                          'extra_depth',
                          'latch_return_dist',
                          'max_travel',
                          'max_z',
                          'xy_clearance',
                          'z_clearance',
                          'side_edge_length',
                          'adj_x',
                          'adj_y',
                          'adj_z',
                          'adj_angle',
                          'diameter_hint',
                          'x_hint_bp',
                          'y_hint_bp',
                          'x_hint_rv',
                          'y_hint_rv',
                          'cal_diameter',
                          'cal_x_width',
                          'cal_y_width',
                          'cal_offset']

        # signal connections
        self.cmb_probe_select.activated.connect(lambda index: self.stackedWidget_probe_buttons.setCurrentIndex(index))
        self.lineEdit_extra_depth.editingFinished.connect(self.get_probe_max_depth)
        self.lineEdit_max_z.editingFinished.connect(self.get_probe_max_depth)
        self.outside_buttonGroup.buttonClicked.connect(self.probe_btn_clicked)
        self.inside_buttonGroup.buttonClicked.connect(self.probe_btn_clicked)
        self.skew_buttonGroup.buttonClicked.connect(self.probe_btn_clicked)
        self.boss_pocket_buttonGroup.buttonClicked.connect(self.boss_pocket_clicked)
        self.ridge_valley_buttonGroup.buttonClicked.connect(self.ridge_valley_clicked)
        self.cal_buttonGroup.buttonClicked.connect(self.cal_btn_clicked)
        self.clear_buttonGroup.buttonClicked.connect(self.clear_results_clicked)
        self.btn_load_probe.pressed.connect(self.load_probe_pressed)
        self.btn_probe_help.pressed.connect(self.probe_help_pressed)

        self.stackedWidget_probe_buttons.setCurrentIndex(0)

        # define validators for all lineEdit widgets
        # this only works when directly typing into a lineEdit
        if INFO.MACHINE_IS_METRIC:
            self.regex = QRegularExpression(r'^((\d{1,4}(\.\d{1,3})?)|(\.\d{1,3}))$')
        else:
            self.regex = QRegularExpression(r'^((\d{1,3}(\.\d{1,4})?)|(\.\d{1,4}))$')
        self.valid = QtGui.QRegularExpressionValidator(self.regex)
        regex = QRegularExpression(r'^\d{0,5}$')
        self.lineEdit_probe_tool.setValidator(QtGui.QRegularExpressionValidator(regex))
        for i in self.parm_list:
            self['lineEdit_' + i].setValidator(self.valid)

        self.event_filter = EventFilter(self)
        self.line_list = self.parm_list[:]
        self.line_list[self.parm_list.index('cal_offset')] = 'probe_tool'
        self.event_filter.set_line_list(self.line_list)
        self.event_filter.set_old_style(self.lineEdit_probe_diam.styleSheet())
        for line in self.line_list:
            self[f'lineEdit_{line}'].installEventFilter(self.event_filter)

    def _hal_init(self):
        def homed_on_status():
            return (STATUS.machine_is_on() and (STATUS.is_all_homed() or INFO.NO_HOME_REQUIRED))
        STATUS.connect('state_off', lambda w: self.setEnabled(False))
        STATUS.connect('state_estop', lambda w: self.setEnabled(False))
        STATUS.connect('interp-idle', lambda w: self.setEnabled(homed_on_status()))
        STATUS.connect('all-homed', lambda w: self.setEnabled(True))

        # must directly initialize
        self.statuslabel_motiontype.hal_init()

        if self.PREFS_:
            self.probe_settings = self.groupBox_parameters.findChildren(QtWidgets.QLineEdit)
            for probe in self.probe_settings:
                probe.setText(self.PREFS_.getpref(probe.objectName(), '10', str, 'PROBE OPTIONS'))

    def _hal_cleanup(self):
        if self.PREFS_:
            LOG.debug('Saving Basic Probe data to preference file.')
            for probe in self.probe_settings:
                self.PREFS_.putpref(probe.objectName(), probe.text(), str, 'PROBE OPTIONS')
        if self.proc is not None: self.proc.terminate()

    def set_test_mode(self):
        self.test_mode = True

    def set_calc_mode(self, mode):
        self.event_filter.set_calc_mode(mode)

#################
# process control
#################
    def start_process(self):
        self.proc = QProcess()
        self.proc.setReadChannel(QProcess.StandardOutput)
        self.proc.started.connect(self.process_started)
        self.proc.readyReadStandardOutput.connect(self.read_stdout)
        self.proc.readyReadStandardError.connect(self.read_stderror)
        self.proc.finished.connect(self.process_finished)
        self.proc.start(f'python3 {SUBPROGRAM}')

    def start_probe(self, cmd):
        if self.test_mode:
            string_to_send = cmd + '$' + json.dumps(self.send_dict) + '\n'
            print(string_to_send)
            return
        if self.proc is not None:
            self.parent.add_status("Probe Routine processor is busy", WARNING)
            return
        if int(self.lineEdit_probe_tool.text()) != STATUS.get_current_tool():
            self.parent.add_status("Probe tool not mounted in spindle", WARNING)
            return
        self.start_process()
        string_to_send = cmd + '$' + json.dumps(self.send_dict) + '\n'
#        print("String to send ", string_to_send)
        STATUS.block_error_polling()
        self.proc.writeData(bytes(string_to_send, 'utf-8'))

    def process_started(self):
        self.parent.add_status(f"Basic_Probe subprogram started with PID {self.proc.processId()}")

    def read_stdout(self):
        qba = self.proc.readAllStandardOutput()
        line = qba.data()
        self.parse_input(line)

    def read_stderror(self):
        qba = self.proc.readAllStandardError()
        line = qba.data()
        self.parse_input(line)

    def process_finished(self, exitCode, exitStatus):
        LOG.debug(f"Probe Process finished - exitCode {exitCode} exitStatus {exitCode}")
        self.proc = None
        STATUS.unblock_error_polling()

    def parse_input(self, line):
        line = line.decode("utf-8")
        if "ERROR INFO" in line:
            text = line.replace("ERROR INFO", "")
            self.parent.add_status(text, WARNING)
        elif "ERROR" in line:
            text = line.replace("ERROR", "")
            #print(line)
            STATUS.unblock_error_polling()
            self.parent.add_status(text, WARNING)
        elif "INFO" in line:
            pass
        elif "PROBE_ROUTINES" in line:
            text = line.replace("PROBE_ROUTINES", "")
            self.parent.add_status(text)
            if LOG.getEffectiveLevel() < logger.INFO:
                print(line)
        elif "COMPLETE" in line:
            STATUS.unblock_error_polling()
            return_data = line.rstrip().split('$')
            data = json.loads(return_data[1])
            self.show_results(data)
            self.parent.add_status("Basic Probing routine completed without errors")
        elif "HISTORY" in line:
            if 'finish' in line:
                text = line.replace("HISTORY", "")
                self.parent.add_status(text, WARNING)
            else:
                self.parent.add_status("Probe history updated to machine log")
        elif "DEBUG" in line:
            pass
        else:
            self.parent.add_status(f"Error parsing return data from sub_processor. Line={line}", WARNING)

# Main button handler routines
    def load_probe_pressed(self):
        try:
            tool =  int(self.lineEdit_probe_tool.text())
        except:
            tool = 0
        if tool > 0:
            info = TOOL.GET_TOOL_INFO(tool)
            dia = info[11]
            self.lineEdit_probe_diam.setText(f"{dia:8.3f}")
            ACTION.CALL_MDI(f"M61 Q{tool}")
        else:
            self.parent.add_status("Invalid probe tool specified", WARNING)

    def probe_help_pressed(self):
        self.help.show()
       
    def probe_btn_clicked(self, button):
        cmd = button.property('probe')
        if cmd == 'probe_xy_hole':
            self.parent.add_status("Use the probe_rectangular_pocket function")
            return
        self.get_parms()
        self.start_probe(cmd)

    def boss_pocket_clicked(self, button):
        cmd = button.property('probe')
        if 'round' in cmd:
            if self.lineEdit_diameter_hint.text() == "":
                self.parent.add_status('Parameter diameter_hint missing', WARNING)
                return
        elif 'rectangular' in cmd:
            for i in ['x_hint_bp', 'y_hint_bp']:
                if self['lineEdit_' + i].text() == "":
                    self.parent.add_status(f'Parameter {i} missing', WARNING)
                    return
        else: return
        self.get_parms()
        self.start_probe(cmd)

    def ridge_valley_clicked(self, button):
        cmd = button.property('probe')
        if 'x' in cmd:
            if self.lineEdit_x_hint_rv.text() == "":
                self.parent.add_status(f'Parameter x_hint_rv missing', WARNING)
                return
        elif 'y' in cmd:
            if self.lineEdit_y_hint_rv.text() == "":
                self.parent.add_status(f'Parameter y_hint_rv missing', WARNING)
                return
        else: return
        self.get_parms()
        self.start_probe(cmd)

    def cal_btn_clicked(self, button):
        cmd = button.property('probe')
        if 'round' in cmd:
            if self.lineEdit_cal_diameter.text() == "":
                self.parent.add_status('Parameter cal_diameter missing', WARNING)
                return
        elif 'square' in cmd:
            for i in ['cal_x_width', 'cal_y_width']:
                if self['lineEdit_' + i].text() == "":
                    self.parent.add_status(f'Parameter {i} missing', WARNING)
                    return
        else: return
        self.get_parms()
        self.start_probe(cmd)

    def clear_results_clicked(self, button):
        cmd = button.property('clear')
        if cmd in dir(self): self[cmd]()

    def clear_x(self):
        self.status_xm.setText('0')
        self.status_xp.setText('0')
        self.status_xc.setText('0')
        self.status_lx.setText('0')

    def clear_y(self):
        self.status_ym.setText('0')
        self.status_yp.setText('0')
        self.status_yc.setText('0')
        self.status_ly.setText('0')

    def clear_all(self):
        self.clear_x()
        self.clear_y()
        self.status_z.setText('0')
        self.status_d.setText('0')
        self.status_delta.setText('0')
        self.status_a.setText('0')

# Helper functions
    def get_probe_max_depth(self):
        if not self.tool_db is None:
            probe_tool = int(self.lineEdit_probe_tool.text())
            extra_depth = float(self.lineEdit_extra_depth.text())
            tool  = float(self.tool_db.get_tool_data(probe_tool, "LENGTH"))
            maxz = float(self.lineEdit_max_z.text())
            depth = maxz + extra_depth
            if depth > tool:
                self.parent.add_status(f"Probing depth {depth} could exceed probe tool length {tool}", WARNING)

    def get_parms(self):
        self.send_dict = {key: self['lineEdit_' + key].text() for key in (self.parm_list)}
        for key in ['allow_auto_zero', 'allow_auto_skew', 'cal_avg_error', 'cal_x_error', 'cal_y_error']:
            val = '1' if self[key].isChecked() else '0'
            self.send_dict.update( {key: val} )

    def show_results(self, line):
        for key in self.status_list:
            self['status_' + key].setText(line[key])
        self.lineEdit_cal_offset.setText(line['offset'])

    ##############################
    # required class boiler code #
    ##############################
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)


class HelpPage(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(HelpPage, self).__init__()
        self.setMinimumWidth(600)
        self.setMinimumHeight(600)
        self.setWindowTitle("BasicProbe Help")
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        self.helpPages = ['basic_help.html','basic_help1.html','basic_help2.html',
                          'basic_help3.html','basic_help4.html','basic_help5.html',
                          'basic_help6.html', 'basic_help7.html','basic_help8.html']
        self.currentHelpPage = 0
        self.build_widget()
        self.update_help_page()
        # signal connections
        self.btn_close.pressed.connect(self.help_close_pressed)
        self.btn_prev.pressed.connect(self.help_prev_pressed)
        self.btn_next.pressed.connect(self.help_next_pressed)

    def build_widget(self):
        main_layout = QtWidgets.QVBoxLayout()
        btn_box = QtWidgets.QHBoxLayout()
        self.btn_prev = QtWidgets.QPushButton('PREV')
        self.btn_next = QtWidgets.QPushButton('NEXT')
        self.btn_close = QtWidgets.QPushButton('CLOSE')
        btn_box.addWidget(self.btn_prev)
        btn_box.addWidget(self.btn_next)
        btn_box.addWidget(self.btn_close)
        self.text_edit = QtWidgets.QTextEdit('Basic Probe Help')
        main_layout.addWidget(self.text_edit)
        main_layout.addLayout(btn_box)
        self.setLayout(main_layout)

    def help_close_pressed(self):
        self.hide()

    def help_prev_pressed(self):
        if self.currentHelpPage == 0: return
        self.currentHelpPage -= 1
        self.update_help_page()

    def help_next_pressed(self):
        if self.currentHelpPage == len(self.helpPages) - 1: return
        self.currentHelpPage += 1
        self.update_help_page()

    def update_help_page(self):
        try:
            pagePath = os.path.join(HELP, self.helpPages[self.currentHelpPage])
            if not os.path.exists(pagePath): raise Exception(f"Missing File: {pagePath}") 
            file = QFile(pagePath)
            file.open(QFile.ReadOnly)
            html = file.readAll()
            html = str(html, encoding='utf8')
#            html = html.replace("../images/widgets/","{}/widgets/".format(INFO.IMAGE_PATH))
            self.text_edit.setHtml(html)
        except Exception as e:
            self.text_edit.setHtml(f'''
<h1 style=" margin-top:18px; margin-bottom:12px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;">
<span style=" font-size:xx-large; font-weight:600;">Basic Probe Help not available</span> </h1>
{e}''')


# sub-classed Calculator so button actions can be redefined
class CalcInput(Calculator):
    apply_action = pyqtSignal()
    next_action = pyqtSignal()
    back_action = pyqtSignal()

    def __init__(self):
        super(CalcInput, self).__init__()
        
    def applyAction(self):
        self.apply_action.emit()

    def nextAction(self):
        self.next_action.emit()

    def backAction(self):
        self.back_action.emit()

    #############################
    # Testing                   #
    #############################
class Testing(object):
    def __init__(self, parent=None):
        super(Testing, self).__init__()

    def add_status(self, msg, level=0):
        print(msg)

if __name__ == "__main__":
# This is just for seeing what the ui looks like
# Nothing will work if linuxcnc isn't running
    from PyQt5.QtWidgets import *
    from PyQt5.QtCore import *
    from PyQt5.QtGui import *
    app = QtWidgets.QApplication(sys.argv)
    p = Testing()
    w = BasicProbe(p)
    w.set_calc_mode(True)
    w.set_test_mode()
    w.show()
    sys.exit( app.exec_() )

