#!/usr/bin/env python3
# Qtvcp basic probe
#
# Copyright (c) 2026  Jim Sloot <persei802@gmail.com>
# Tool Measure code added 2026 by Jim Sloot
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
import zmq
import hal

from lib.event_filter import EventFilter
from qtpy.QtGui import QRegExpValidator
from qtpy.QtCore import QProcess, QEvent, QObject, QRegExp, QFile, Qt, QThread, QSettings, Signal, Slot
from qtpy.QtWidgets import QWidget, QPushButton, QTextEdit
from qtpy import uic

from qtvcp.widgets.widget_baseclass import _HalWidgetBase
from qtvcp.core import Action, Status, Info, Path, Tool
from qtvcp import logger

ACTION = Action()
STATUS = Status()
INFO = Info()
TOOL = Tool()
PATH = Path()
HERE = os.path.dirname(os.path.abspath(__file__))
LOG = logger.getLogger(__name__)
# setting log level to DEBUG enables the simulated probe button for testing
LOG.setLevel(logger.INFO) # One of DEBUG, INFO, WARNING, ERROR, CRITICAL
VERSION = '2.1'

SUBPROGRAM = os.path.join(HERE, 'probe_subprog.py')
HELP = os.path.join(PATH.CONFIGPATH, "help_files")

# StatusBar message alert levels
DEFAULT =  0
WARNING =  1
ERROR = 2


class ProbeWorker(QObject):
    finished = Signal(dict)
    error = Signal(str)
    
    def __init__(self):
        super().__init__()

    @Slot(dict)
    def execute(self, message):
        try:
            self.socket.send_json(message)
            reply = self.socket.recv_json()
            self.finished.emit(reply)
        except Exception as e:
            self.error.emit(str(e))

    def connect_socket(self):
        self.context = zmq.Context.instance()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect("ipc:///tmp/probe_routines.sock")
        
class BasicProbe(QWidget, _HalWidgetBase):
    startProbe = Signal(dict)

    def __init__(self, parent=None):
        super(BasicProbe, self).__init__()
        self.parent = parent
        self.settings = QSettings('qtdragon', 'plugins')
        self.helpfile = os.path.join(HELP, 'basic_probe_help.html')
        self.context = None
        self.dialog_code = 'CALCULATOR'
        self.tool_code = 'TOOLCHOOSER'
        self.tool_diameter = None
        self.tool_number = None
        self.probe_busy = False
        self.proc = None
        self.default_style = ''
        self.red_border = "border: 2px solid red;"
        self.regex = ''
        # calculated tool measure values
        self.ts_zero = 0
        self.ts_tlo = 0
        # tool measure returned values
        self.ts_diam = 0
        self.ts_th = 0
        self.ts_bh = 0
        
        self.debug_mode = LOG.getEffectiveLevel()
        self.tmpl = '.3f' if INFO.MACHINE_IS_METRIC else '.4f'
        try:
            self.tool_db = self.parent.tool_db
        except Exception as e:
            print(e)
            self.tool_db = None
        
        # load the widgets ui file
        self.filename = os.path.join(HERE, 'basic_probe.ui')
        try:
            self.instance = uic.loadUi(self.filename, self)
        except AttributeError as e:
            LOG.critical(e)

        if self.debug_mode != 10:
            self.btn_probe.hide()
        self.probe_page_list = {'OUTSIDE MEASUREMENTS': (False, False),
                                'INSIDE MEASUREMENTS': (False, False),
                                'ANGLE MEASUREMENTS': (True, False),
                                'BOSS AND POCKET': (False, True),
                                'RIDGE AND VALLEY': (False, True),
                                'CALIBRATION': (False, True),
                                'TOOL MEASURE': (False, False)}

        # populate probe page combobox
        self.cmb_probe_select.clear()
        for key, val in self.probe_page_list.items():
            self.cmb_probe_select.addItem(key, val)
        self.probe_select_changed(0)
        self.cmb_probe_select.wheelEvent = lambda event: None
        self.status_list = ['xm', 'xc', 'xp', 'ym', 'yc', 'yp', 'lx', 'ly', 'z', 'd', 'a', 'delta', 'offset']
        #create message dictionaries to send via zmq
        self.parm_dict = {} # probe parameters
        self.cbox_dict = {} # checkboxes
        self.data_dict = {} # tool setter data
        # this is also the order of the next widget when calculator 'next' button is pressed
        self.parm_list = ['probe_diam',
                          'rapid_vel',
                          'search_vel',
                          'probe_vel',
                          'extra_depth',
                          'retract',
                          'max_travel',
                          'xy_clearance',
                          'stepoff',
                          'max_z',
                          'z_clearance',
                          'adj_x',
                          'adj_y',
                          'adj_z',
                          'adj_angle',
                          'edge_width',
                          'x_hint',
                          'y_hint',
                          'diameter_hint']

        self.event_filter = EventFilter(self)
        for line in self.parm_list:
            self[f'lineEdit_{line}'].installEventFilter(self.event_filter)
        self.lineEdit_probe_tool.installEventFilter(self.event_filter)
        self.lineEdit_ref_tool.installEventFilter(self.event_filter)
        self.lineEdit_tool_number.installEventFilter(self.event_filter)
        self.event_filter.set_line_list(self.parm_list)
        self.event_filter.set_tool_list(['probe_tool', 'tool_number', 'ref_tool'])
        self.event_filter.set_parms(('_basicprobe_', True))

        # signal connections
        self.chk_use_calculator.stateChanged.connect(lambda state: self.event_filter.set_dialog_mode(state))
        self.cmb_probe_select.activated.connect(lambda index: self.probe_select_changed(index))
        self.lineEdit_probe_tool.returnPressed.connect(lambda b=self.lineEdit_probe_tool: self.load_tool_pressed(b))
        self.lineEdit_tool_number.returnPressed.connect(lambda b=self.lineEdit_tool_number: self.load_tool_pressed(b))
        self.lineEdit_ref_tool.returnPressed.connect(self.change_ref_tool)
        self.lineEdit_extra_depth.returnPressed.connect(self.get_probe_max_depth)
        self.lineEdit_max_z.returnPressed.connect(self.get_probe_max_depth)
        self.outside_buttonGroup.buttonClicked.connect(self.start_probe)
        self.inside_buttonGroup.buttonClicked.connect(self.start_probe)
        self.skew_buttonGroup.buttonClicked.connect(self.start_probe)
        self.boss_pocket_buttonGroup.buttonClicked.connect(self.start_probe)
        self.ridge_valley_buttonGroup.buttonClicked.connect(self.start_probe)
        self.cal_buttonGroup.buttonClicked.connect(self.start_probe)
        self.clear_buttonGroup.buttonClicked.connect(self.clear_results_clicked)
        self.btn_probe_help.pressed.connect(lambda: self.parent.show_probe_help(self.helpfile))
        self.btn_measure_tool.pressed.connect(self.measure_tool)
        self.stackedWidget_probe_buttons.setCurrentIndex(0)
        if self.debug_mode == 10:
            self.btn_probe.pressed.connect(self.test_probe)
            self.btn_probe.released.connect(self.test_probe)

        # define validators for all lineEdit widgets
        # this only works when directly typing into a lineEdit
        if INFO.MACHINE_IS_METRIC:
            self.regex = QRegExp(r'^((\d{1,4}(\.\d{1,3})?)|(\.\d{1,3}))$')
        else:
            self.regex = QRegExp(r'^((\d{1,3}(\.\d{1,4})?)|(\.\d{1,4}))$')
        self.valid = QRegExpValidator(self.regex)
        regex = QRegExp(r'^\d{0,5}$')
        self.lineEdit_probe_tool.setValidator(QRegExpValidator(regex))
        self.lineEdit_ref_tool.setValidator(QRegExpValidator(regex))
        for i in self.parm_list:
            self['lineEdit_' + i].setValidator(self.valid)

        # restore probe parameters from settings
        for parm in self.parm_list:
            self[f'lineEdit_{parm}'].setText(self.settings.value(f'basic_probe/{parm}', '0', str))
        self.ts_zero = float(self.settings.value('basic_probe/zero_reference', '0.0', str))
        self.lineEdit_probe_tool.setText(self.settings.value('basic_probe/probe_tool', '99', str))
        self.lineEdit_ref_tool.setText(self.settings.value('basic_probe/reference_tool', '0', str))
        self.lineEdit_tool_number.setText(self.settings.value('basic_probe/tool_number', '0', str))
        self.lineEdit_ts_zero.setText(f"{abs(self.ts_zero):{'.3f'}}")
        # data for tool measure routine
        try:
            self.data_dict['ts_x'] = float(self.parent.w.lineEdit_sensor_x.text())
            self.data_dict['ts_y'] = float(self.parent.w.lineEdit_sensor_y.text())
            self.data_dict['ts_z'] = float(self.parent.w.lineEdit_sensor_height.text())
            self.data_dict['ts_max'] = float(self.lineEdit_max_z.text())
            self.data_dict['ref_tool'] = int(self.lineEdit_ref_tool.text())
            self.data_dict['tool_number'] = int(self.lineEdit_tool_number.text())
        except AttributeError as e:
            print('Error setting data dictionary: ', e)
        self.lineEdit_ts_height.setText(f"{self.data_dict['ts_z']}")

        LOG.info(f"Using Basic Probe version {VERSION}")
        self.start_process()
        self.start_zmq()

    def _hal_init(self):
        def homed_on_status():
            return (STATUS.machine_is_on() and (STATUS.is_all_homed() or INFO.NO_HOME_REQUIRED))
        STATUS.connect('general', self.dialog_return)
        STATUS.connect('state_off', lambda w: self.setEnabled(False))
        STATUS.connect('state_estop', lambda w: self.setEnabled(False))
        STATUS.connect('interp-idle', lambda w: self.setEnabled(homed_on_status()))
        STATUS.connect('all-homed', lambda w: self.setEnabled(True))
        self.default_style = self.lineEdit_probe_diam.styleSheet()

        # must directly initialize
        self.statuslabel_motiontype.hal_init()

        # create HAL pin for simulated probe signal
        oldname = self.HAL_GCOMP_.comp.getprefix()
        self.HAL_GCOMP_.comp.setprefix('qtbasicprobe')
        self.probe_out = self.HAL_GCOMP_.newpin("probe-out", hal.HAL_BIT, hal.HAL_OUT)
        self.HAL_GCOMP_.comp.setprefix(oldname)

    def _hal_cleanup(self):
        LOG.debug('Saving Basic Probe data to Settings.')
        for parm in self.parm_list:
            self.settings.setValue(f'basic_probe/{parm}', self[f'lineEdit_{parm}'].text())
        self.settings.setValue('basic_probe/zero_reference', str(self.ts_zero))
        self.settings.setValue('basic_probe/probe_tool', self.lineEdit_probe_tool.text())
        self.settings.setValue('basic_probe/reference_tool', self.lineEdit_ref_tool.text())
        self.settings.setValue('basic_probe/tool_number', self.lineEdit_tool_number.text())
        self.settings.sync()

        if self.proc is not None: self.proc.terminate()
        self.probe_thread.quit()
        self.probe_thread.wait()

# STATUS messages
    def dialog_return(self, w, message):
        rtn = message['RETURN']
        name = message.get('NAME')
        obj = message.get('OBJECT')
        code = bool(message.get('ID') == '_basicprobe_')
        next = message.get('NEXT', False)
        back = message.get('BACK', False)
        if code and name == self.dialog_code:
            obj.setStyleSheet(self.default_style)
            if rtn is not None:
                LOG.debug(f'message return:{message}')
                obj.setText(f'{rtn:{self.tmpl}}')
            # request for next input widget from linelist
            if next:
                newobj = self.event_filter.findNext()
                self.event_filter.show_calc(newobj, True)
            elif back:
                newobj = self.event_filter.findBack()
                self.event_filter.show_calc(newobj, True)
        elif code and name == self.tool_code:
            obj.setStyleSheet(self.default_style)
            if rtn is not None:
                obj.setText(str(int(rtn)))
                if obj == self.lineEdit_ref_tool:
                    self.change_ref_tool()
                else:
                    self.load_tool_pressed(obj)

    def _tool_info(self, data):
        if data.id != -1:
            self.tool_diameter = data.diameter
            self.tool_number = data.id
            return
        self.tool_diameter = None
        self.tool_number = None

    def set_calc_mode(self, mode):
        self.event_filter.set_dialog_mode(mode)

#################
# process control
#################
    def start_process(self):
        self.proc = QProcess()
        self.proc.setReadChannel(QProcess.StandardOutput)
        self.proc.errorOccurred.connect(self.process_error)
        self.proc.started.connect(self.process_started)
        self.proc.readyReadStandardOutput.connect(self.read_stdout)
        self.proc.readyReadStandardError.connect(self.read_stderror)
        self.proc.finished.connect(self.process_finished)
        self.proc.start(sys.executable, [SUBPROGRAM])

    def read_stdout(self):
        qba = self.proc.readAllStandardOutput()
        line = qba.data()
        print('Stdout: ', line)

    def read_stderror(self):
        qba = self.proc.readAllStandardError()
        line = qba.data()
# uncomment to get error messages from probe_subprog 
#        print('Stderr: ', line)

    def process_started(self):
        self.parent.add_status(f"Basic_Probe subprogram started with PID {self.proc.processId()}")
        self.probe_thread.start()

    def process_finished(self, exitCode, exitStatus):
        LOG.debug(f"Probe Process finished - exitCode {exitCode} exitStatus {exitCode}")
        self.proc = None

    def process_error(self, error):
        print('Process Error ', error)
        print(self.proc.errorString())

    def start_zmq(self):
        self.probe_thread = QThread(self)
        self.worker = ProbeWorker()
        self.startProbe.connect(self.worker.execute)
        self.worker.finished.connect(self.parse_reply)
        self.worker.error.connect(self.parse_error)
        self.probe_thread.started.connect(self.worker.connect_socket)
        self.worker.moveToThread(self.probe_thread)

    def start_probe(self, button):
        cmd = button.property('probe')
        if self.probe_busy:
            self.parent.add_status("Probe Routine processor is busy", WARNING)
            return
        if cmd.startswith('probe'):
            if int(self.lineEdit_probe_tool.text()) != STATUS.get_current_tool():
                self.parent.add_status("Probe tool not mounted in spindle", WARNING)
                return
        error = self.get_parms()
        if error is not None:
            self.parent.add_status(f'Error in parameter data: {error}', WARNING)
            return
        msg = {'cmd': cmd,
               'params': self.parm_dict,
               'checks': self.cbox_dict}
        if cmd.startswith('tool'):
            msg['tsdata'] = self.data_dict
        self.startProbe.emit(msg)
        self.probe_busy = True

    def parse_reply(self, reply):
        if reply['status'] == 'ERROR':
            self.parent.add_status(reply['error'], WARNING)
        elif reply['status'] == 'EXCEPTION':
            print('Exception: ', reply['error'])
            print('Traceback ', reply['traceback'])
        elif reply['status'] == 'COMPLETE':
            if 'results' in reply:
                status = reply['results']
                for key in status.keys():
                    if status[key] is not None:
                        val = f'{status[key]:{self.tmpl}}'
                        self[f'status_{key}'].setText(val)
            if 'ts_status' in reply:
                ts_status = reply['ts_status']
                print('ts_status ', ts_status)
                for key in ts_status.keys():
                    if ts_status[key] is not None:
                        val = ts_status[key]
                        self[f'ts_{key}'] = val
                self.set_tool_offset()
            if 'history' in reply:
                history = reply['history']
                STATUS.emit('update-machine-log', history, 'TIME')
            self.parent.add_status("Basic Probe routine completed without errors")
        else:
            self.parent.add_status("Error parsing reply from sub_processor.", WARNING)
        self.probe_busy = False

    def parse_error(self, error):
        self.parent.add_status(error, ERROR)

# Main button handler routines
    def measure_tool(self):
        try:
            self.data_dict['ref_tool'] = int(self.lineEdit_ref_tool.text())
            self.data_dict['tool_number'] = int(self.lineEdit_tool_number.text())
        except (KeyError, ValueError) as e:
            self.parent.add_status(f'Measure tool error: {e}', ERROR)
            return
        self.start_probe(self.btn_measure_tool)

    def clear_results_clicked(self, button):
        cmd = button.property('clear')
        if cmd in dir(self): self[cmd]()

    def clear_x(self):
        for i in ['xm', 'xp', 'xc', 'lx']:
            self[f'status_{i}'].setText('---')

    def clear_y(self):
        for i in ['ym', 'yp', 'yc', 'ly']:
            self[f'status_{i}'].setText('---')

    def clear_all(self):
        self.clear_x()
        self.clear_y()
        for i in ['z', 'd', 'delta', 'a']:
            self[f'status_{i}'].setText('---')

# Helper functions
    def change_ref_tool(self):
        ref_tool = int(self.lineEdit_ref_tool.text())
        if ref_tool != self.data_dict['ref_tool']:
            self.parent.add_status('Changing the reference tool will require all tools to be re-measured', WARNING)
        self.data_dict['ref_tool'] = ref_tool
        self.lineEdit_probe_tool.setText(str(ref_tool))
        self.load_tool_pressed(self.lineEdit_ref_tool)

    def load_tool_pressed(self, obj):
        if obj == self.lineEdit_tool_number:
            self.lineEdit_probe_tool.setText(obj.text())
        elif obj == self.lineEdit_probe_tool:
            self.lineEdit_tool_number.setText(obj.text())
        tool = int(obj.text())
        info = TOOL.GET_TOOL_INFO(tool)
        self.lineEdit_ts_tlo.setText(f"{info[4]:8.3f}")
        self.lineEdit_probe_diam.setText(f"{info[11]:8.3f}")
        self.lineEdit_tool_number.setText(obj.text())
        ACTION.CALL_MDI_WAIT(f'M61 Q{tool} G49', mode_return=True)

    def test_probe(self):
        if self.btn_probe.isDown():
            self.probe_out.set(True)
        else:
            self.probe_out.set(False)

    def probe_select_changed(self, index):
        self.stackedWidget_probe_buttons.setCurrentIndex(index)
        state = self.cmb_probe_select.itemData(index)
        self.widget_edge_width.setVisible(state[0])
        self.widget_hints.setVisible(state[1])
        self.widget_cal_error.setVisible(state[1])
        if self.cmb_probe_select.currentText() == 'TOOL MEASURE':
            self.lbl_probe_tool.setText('TOOL\nNUMBER')
            self.lbl_probe_diameter.setText('TOOL\nDIAMETER')
        else:
            self.lbl_probe_tool.setText('PROBE\nTOOL')
            self.lbl_probe_diameter.setText('PROBE\nDIAMETER')

    def get_probe_max_depth(self):
        if self.tool_db is not None:
            probe_tool = int(self.lineEdit_probe_tool.text())
            extra_depth = float(self.lineEdit_extra_depth.text())
            data = self.tool_db.get_tool_data(probe_tool)
            tool = data['length']
            maxz = float(self.lineEdit_max_z.text())
            depth = maxz + extra_depth
            if depth > tool:
                self.parent.add_status(f"Probing depth {depth} could exceed probe tool length {tool}", WARNING)

    def get_parms(self):
        for key in self.parm_list:
            try:
                self.parm_dict[key] = float(self[f'lineEdit_{key}'].text())
                self[f'lineEdit_{key}'].setStyleSheet(self.default_style)
            except ValueError as e:
                self[f'lineEdit_{key}'].setStyleSheet(self.red_border)
                return str(e)
        self.parm_dict['cal_offset'] = float(self.status_offset.text())

        for key in ['allow_auto_zero', 'allow_auto_skew', 'cal_avg_error', 'cal_x_error', 'cal_y_error']:
            self.cbox_dict[key] = self[key].isChecked()
        # add on tool measure data
        # do some safety checks on the parameters
        if self.parm_dict['retract'] >= self.parm_dict['stepoff']:
            return 'Stepoff must be greater than retract'
        if self.parm_dict['rapid_vel'] < self.parm_dict['search_vel']:
            return 'Rapid probe must be greater than search probe'
        if self.parm_dict['search_vel'] < self.parm_dict['probe_vel']:
            return 'Search probe must be greater than probe velocity'
        return None

    def set_tool_offset(self):
        if self.lineEdit_tool_number.text() == self.lineEdit_ref_tool.text():
            self.ts_zero = self.ts_th
            self.lineEdit_ts_zero.setText(f'{self.ts_zero:.3f}')
            self.lineEdit_ts_tlo.clear()
            self.parent.add_status(f"Set reference tool {self.data_dict['ref_tool']} to value {self.ts_zero:.3f}")
        else:
            self.ts_tlo = self.ts_zero - self.ts_th
            self.lineEdit_ts_tlo.setText(f'{self.ts_tlo:.3f}')
            ACTION.CALL_MDI(f"G10 L1 P{self.data_dict['tool_number']} Z{self.ts_tlo:.3f}")
            self.parent.add_status(f"Set tool length offset for tool {self.data_dict['tool_number']} to {self.ts_tlo:.3f}")
            # have to do this here because tool table data_changed is not emitted with a G10
            if self.tool_db is not None:
                data = TOOL.GET_TOOL_INFO(self.data_dict['tool_number'])
                self.tool_db.update_tool_table(data[0], (data[4], data[11], data[15]))
        ACTION.CALL_MDI('G53 G0 Z0')

    ##############################
    # required class boiler code #
    ##############################
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)


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
    from qtpy.QtWidgets import QApplication
    app = QApplication(sys.argv)
    p = Testing()
    w = BasicProbe(p)
    w.set_calc_mode(True)
    w.lineEdit_probe_tool.setEnabled(False)
    w.show()
    sys.exit( app.exec_() )

