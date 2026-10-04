#!/usr/bin/env python3
# QtDragon probe subprogram
#
# Copyright (c) 2026  Jim Sloot <persei802@gmail.com>
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
# This subprogram can be used by both versa_probe and basic_probe widgets

import sys
import zmq
import traceback
import linuxcnc

from qtpy.QtCore import QObject
from qtvcp.core import Status, Info
from probe_routines import ProbeRoutines
from tool_routines import ToolRoutines

STATUS = Status()
INFO = Info()


class ProbeSubprog(QObject, ProbeRoutines, ToolRoutines):
    def __init__(self):
        QObject.__init__(self)
        ProbeRoutines.__init__(self)
        ToolRoutines.__init__(self)
        self.cmd = linuxcnc.command()
        self.stat = linuxcnc.stat()
        self.error_channel = linuxcnc.error_channel()
        self.commands = list()
        self.tmpl = '.3f' if INFO.MACHINE_IS_METRIC else '.4f'
        self.parms = {} # probe parameters
        self.cbox = {}  # checkboxes
        self.status = {} # probe results to return to main program
        self.ts_data = {}  # tool setter data
        self.ts_status = {} # tool setter results to send to main program
        self.status_list = ['xm', 'xc', 'xp', 'ym', 'yc', 'yp', 'lx', 'ly', 'z', 'd', 'a', 'delta', 'offset']
        self.history_log = ""

        self.context = zmq.Context.instance()
        self.socket = self.context.socket(zmq.REP)
        self.socket.bind("ipc:///tmp/probe_routines.sock")
        self.process()

    def process(self):
        while True:
            msg = self.socket.recv_json()
            try:
                error = self.process_command(msg)
                # error = 1 means success,
                # error = None means ignore,
                # anything else is an error - a returned string is an error message
                if error is not None:
                    if error != 1:
                        text = error if type(error) == str else 'Probe routine returned with error'
                        self.socket.send_json({'status': 'ERROR', 'error': text})
                    else:
                        reply = {'status': 'COMPLETE',
                                 'results': self.status}
                        if len(self.ts_status) > 0:
                            reply['ts_status'] = self.ts_status
                        if self.history_log:
                            reply['history'] = self.history_log
                            self.history_log = ''
                        self.socket.send_json(reply)
            except Exception as e:
                self.socket.send_json({
                    'status': 'EXCEPTION',
                    'error': str(e),
                    'traceback': traceback.format_exc()
                    })
                
    def process_command(self, msg):
        cmd = msg['cmd']
        if cmd in dir(self):
            if not STATUS.is_on_and_idle(): return None
            pre = self.prechecks()
            if pre is not None: return pre
            msg_ok = False
            if 'params' in msg:
                self.parms = msg['params']
                msg_ok = True
            if 'checks' in msg:
                self.cbox = msg['checks']
                msg_ok = True
            if 'tsdata' in msg:
                self.ts_data = msg['tsdata']
                self.ts_status.clear()
                msg_ok = True
            if not msg_ok:
                return "message does not contain any data"
            self.update_data()
            error = self[cmd]()
            if (error != 1 or type(error) == str) and STATUS.is_on_and_idle():
                self.CALL_MDI_WAIT("G90")
            self.postreset()
            return error
        else:
            return f'Command function {cmd} not in probe routines'

    def update_data(self):
        self.allow_auto_zero = self.cbox['allow_auto_zero']
        self.allow_auto_skew = self.cbox['allow_auto_skew']
        self.cal_avg_error = self.cbox['cal_avg_error']
        self.cal_x_error = self.cbox['cal_x_error']
        self.cal_y_error = self.cbox['cal_y_error']
        self.probe_radius = (self.parms['probe_diam'] + self.parms['cal_offset']) / 2
        for key in self.status_list:
            self.status[key] = None

    def prechecks(self):
        # This is a work around. If a user sets the spindle running in MDI
        # but turn it off with a manual button, then when M72 will turn the
        # spindle back on! So we explicitly set M5 here.
        self.CALL_MDI_WAIT('M5')
        # record current G,S,M codes
        self.CALL_MDI_WAIT('M70')
        # set proper mode based on what machine is based
        if INFO.MACHINE_IS_METRIC and STATUS.is_metric_mode():
            return None
        if not INFO.MACHINE_IS_METRIC and not STATUS.is_metric_mode():
            return None
        if INFO.MACHINE_IS_METRIC:
            self.CALL_MDI_WAIT('g21')
        else:
            self.CALL_MDI_WAIT('g20')
        return None

    # return to previous motion modes
    def postreset(self):
        self.CALL_MDI_WAIT('M72')

    def CALL_MDI_WAIT(self, code):
        self.cmd.mode(linuxcnc.MODE_MDI)
        for line in code.split("\n"):
            self.cmd.mdi(line)
            result = self.cmd.wait_complete(self.timeout)
            try:
                error = self.error_channel.poll()
                if error is not None:
                    self.cmd.abort()
                    return error[1]
            except Exception as e:
                self.cmd.abort()
                return f'{e}'

            if result == -1:
                self.cmd.abort()
                return f'Command timed out: ({self.timeout} seconds)'
            elif result == linuxcnc.RCS_ERROR:
                self.cmd.abort()
                return 'MDI_COMMAND_WAIT RCS error'
        return 1

    def cmdList(self):
        for cmd in self.commands:
            if isinstance(cmd, str):
                rtn = self.CALL_MDI_WAIT(cmd)
            elif callable(cmd):
                rtn = cmd()
            elif isinstance(cmd, (tuple, list)) and callable(cmd[0]):
                rtn = cmd[0](*cmd[1:])
            else:
                raise TypeError(f'Unknown command type {type(cmd)}')
                rtn = 'TypeError Raised'
            if rtn != 1:
                print(f"Command {cmd} failed: {rtn}", flush=True)
                self.commands.clear()
                return rtn
        self.commands.clear()
        return 1

########################################
# required boiler code
########################################
    def __getitem__(self, item):
        return getattr(self, item)
    def __setitem__(self, item, value):
        return setattr(self, item, value)

####################################
# Testing
####################################
if __name__ == "__main__":
    try:
        w = ProbeSubprog()
    except Exception:
        traceback.print_exc()
        raise
