#!/usr/bin/env python3
# Qtvcp - common probe routines
# Copyright (c) 2018  Chris Morley <chrisinnanaimo@hotmail.com>
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

import sys
import time
import select
import math
import linuxcnc
from qtvcp.core import Status, Action
from qtvcp import logger
LOG = logger.getLogger(__name__)
LOG.setLevel(logger.INFO) # One of DEBUG, INFO, WARNING, ERROR, CRITICAL

ACTION = Action()
STATUS = Status()

class ProbeRoutines():
    def __init__(self):
        self.timeout = 30

##################
# Helper Functions
##################

    def set_timeout(self, time):
        self.timeout = time

    def z_clearance_up(self):
        z_stack = self.data_z_clearance + self.data_probe_diam + self.data_extra_depth
        s = f"""G91
        G1 Z{z_stack} F{self.data_rapid_vel}
        G90"""
        return self.CALL_MDI_WAIT(s, self.timeout)

    def z_clearance_down(self):
        z_stack = self.data_z_clearance + self.data_probe_diam  + self.data_extra_depth
        s = f"""G91
        G1 Z-{z_stack} F{self.data_rapid_vel} 
        G90"""
        return self.CALL_MDI_WAIT(s, self.timeout)

    # when probing tool diameter
    def raise_tool_depth(self):
        # move Z+
        s = f"""G91
        G1 F{self.data_rapid_vel} Z{self.data_z_clearance}
        G90"""
        return self.CALL_MDI_WAIT(s, self.timeout)

    # when probing tool diameter
    def lower_tool_depth(self):
        # move Z-
        s = f"""G91
        G1 F{self.data_rapid_vel} Z-{self.data_z_clearance}
        G90"""
        return self.CALL_MDI_WAIT(s, self.timeout)

    def length_x(self):
        if self.status_xp is None: self.status_xp = 0
        if self.status_xm is None: self.status_xm = 0
        if self.status_xp == 0 or self.status_xm == 0: return 0
        self.status_lx = abs(self.status_xm - self.status_xp)
        return self.status_lx

    def length_y(self):
        if self.status_yp is None: self.status_yp = 0
        if self.status_ym is None: self.status_ym = 0
        if self.status_yp == 0 or self.status_ym == 0: return 0
        self.status_ly = abs(self.status_ym - self.status_yp)
        return self.status_ly

    def set_zero(self, s):
        if self.allow_auto_zero is True:
            c = "G10 L20 P0"
            if "X" in s:
                c += f" X{self.data_adj_x}"
            if "Y" in s:
                c += f" Y{self.data_adj_y}"
            if "Z" in s:
                c += f" Z{self.data_adj_z}"
            ACTION.CALL_MDI(c)
            ACTION.RELOAD_DISPLAY()

    def rotate_coord_system(self, a=0.):
        self.status_a = a
        if self.allow_auto_skew is True:
            s = "G10 L2 P0"
            if self.allow_auto_zero is True:
                s += f" X{self.data_adj_x}"
                s += f" Y{self.data_adj_y}"
            else:
                STATUS.stat.poll()
                x = STATUS.stat.position[0]
                y = STATUS.stat.position[1]
                s += f" X{x}"     
                s += f" Y{y}"     
            s +=  f" R{a}"
            self.CALL_MDI_WAIT(s, self.timeout)
            ACTION.RELOAD_DISPLAY()

    def add_history(self, *args):
        if len(args) == 13:
            tpl = '%.3f' if STATUS.is_metric_mode() else '%.4f'
            c = args[0]
            list = ['Xm', 'Xc', 'Xp', 'Lx', 'Ym', 'Yc', 'Yp', 'Ly', 'Z', 'D', 'A']
            for i in range(0, len(list)):
                if list[i] in args[1]:
                    c += ' ' + list[i] + "[" + tpl%(args[i+2]) + ']'
            self.history_log = c
        else:
            # should be a single string
            self.history_log = args[0]

    def probe(self, name):
        if name == "xminus" or name == "yminus" :
            travel = 0 - self.data_max_travel
            latch = 0 - self.data_latch_return_dist
        elif name == "xplus" or name == "yplus":
            travel = self.data_max_travel
            latch = self.data_latch_return_dist
        else:
            return 'invalid probe name'
        axis = name[0].upper()
        laxis = name[0].lower()
        # save current position so we can return to it
        rtn = self.CALL_MDI_WAIT(f'#<{laxis}> = #<_{laxis}>', self.timeout)
        # probe toward target
        s = f"""G91
        G38.2 {axis}{travel} F{self.data_search_vel}"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout)
        if rtn != 1:
            return rtn
        # retract
        s = f"G1 {axis}{-latch} F{self.data_rapid_vel}"
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return rtn
        # wait then probe again at slower speed
        s = f"""G4 P0.5
        G38.2 {axis}{1.2 * latch} F{self.data_probe_vel}"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return rtn
        # retract to original position
        s = f"G90 G1 {axis}#<{laxis}> F{self.data_rapid_vel}"
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return rtn
        return 1

    def CALL_MDI_LIST(self, codeList):
        for s in codeList:
            # call the gcode in MDI
            if type(s) is str:
                rtn = self.CALL_MDI_WAIT(s, self.timeout)
            # call the function directly
            else:
                rtn = s()
            if rtn != 1:
                return f'failed: {rtn} cmd: {s}'
        return 1

    def CALL_MDI_WAIT(self, code, timeout = 5):
        LOG.debug(f'MDI_WAIT_COMMAND= {code}, maxt = {timeout}')
        for l in code.split("\n"):
            ACTION.CALL_MDI( l )
            result = ACTION.cmd.wait_complete(timeout)
            try:
                # give a chance for the error message to get to stdin
                time.sleep(.1)
                error = STATUS.ERROR.poll()
                if not error is None:
                    ACTION.ABORT()
                    return error[1]
            except Exception as e:
                ACTION.ABORT()
                return f'{e}'

            if result == -1:
                ACTION.ABORT()
                return f'Command timed out: ({timeout} seconds)'
            elif result == linuxcnc.RCS_ERROR:
                ACTION.ABORT()
                return 'MDI_COMMAND_WAIT RCS error'
        return 1

    #####################
    # Tool Setter probing
    #####################
    def goto_toolsetter(self):
        try:
            # basic sanity check
            for test in('z_max_clear','ts_x','ts_y','ts_z','ts_max'):
                if self[f'data_{test}'] is None:
                    return f'Missing toolsetter setting: {test}'

            # raise to safe Z height
            # move to tool setter (XY then Z)
            # offset X by tool radius (from toolfile)

            cmdList = []
            cmdList.append(f'F{self.data_rapid_vel}')
            cmdList.append(f'G53 G1 Z{self.data_z_max_clear}')
            cmdList.append(f'G53 G1 X{self.data_ts_x} Y{self.data_ts_y}')
            cmdList.append(f'G53 G1 Z{self.data_ts_z}')
            # call each command - if fail report the error and gcode command
            rtn = self.CALL_MDI_LIST(cmdList)
            if rtn != 1:
                return rtn
            # report success
            return 1
        except Exception as e:
            return f'{e}'

    def wait(self):
        rtn = self.CALL_MDI_WAIT('G4 p 5', self.timeout) 
        if rtn != 1:
            return f'failed: {rtn}'
        return 1

    def probe_tool_z(self):
        return self.probe_tool_with_toolsetter()

    def probe_tool_with_toolsetter(self):
        try:
            # basic sanity checks
            for test in('ts_x','ts_y','ts_z','ts_max','ts_diam','tool_probe_height', 'tool_block_height'):
                if self[f'data_{test}'] is None:
                    return f'Missing toolsetter setting: {test}'
            if self.data_tool_diameter is None or self.data_tool_number is None:
                return 'No tool diameter found'

            # see if we need to offset for tool diameter
            # if so see if there is enough room in X axis limits
            if self.data_tool_diameter > self.data_ts_diam:
                # if close to edge of machine X, offset in the opposite direction
                xplimit = float(INFO.INI.find('AXIS_X','MAX_LIMIT'))
                xmlimit = float(INFO.INI.find('AXIS_X','MIN_LIMIT'))
                if not (self.data_tool_diameter/2 + self.data_ts_x) > xplimit:
                    Xoffset = self.data_tool_diameter/2
                elif not (self.data_ts_x -(self.data_tool_diameter/2)) < xmlimit:
                    Xoffset = 0 - self.data_tool_diameter/2
                else:
                    return 'cannot offset enough in X for tool diameter'
            else: Xoffset = 0

            # offset X by tool radius (from toolfile) if required
            # probe Z
            # raise Z clear
            # move back X by tool radius if required

            cmdList = []
            cmdList.append(f'F{self.data_rapid_vel}')
            cmdList.append('G49')
            cmdList.append('G91')
            # should start spindle in proper direction/speed here..
            cmdList.append(f'G1 X{Xoffset}')
            cmdList.append(f'G38.2 Z-{self.data_ts_max} F{self.data_search_vel}')
            cmdList.append(f'G1 Z{self.data_latch_return_dist} F{self.data_rapid_vel}')
            cmdList.append(f'F{self.data_probe_vel}')
            cmdList.append(f'G38.2 Z-{self.data_latch_return_dist * 1.2}')
            cmdList.append('#<touch_result> = #5063')
            # adjustment to G53 number
            cmdList.append('#<zworkoffset> = [#[5203 + #5220 *20] + #5213 * #5210]')
            cmdList.append(f'G10 L1 P#5400  Z[#5063 + #<zworkoffset> - {self.data_tool_probe_height}]')
            cmdList.append(f'G1 Z{self.data_z_clearance} F{self.data_rapid_vel}')
            cmdList.append(f'G1 X{-Xoffset}')
            cmdList.append('G90')
            cmdList.append('G43')
            # call each command - if fail report the error and gcode command
            rtn = self.CALL_MDI_LIST(cmdList)
            if rtn != 1:
                return rtn
            h = STATUS.get_probed_position()[2]
            self.status_z = h
            p = self.data_tool_probe_height
            toffset = (h-p)
            self.add_history(f'''ToolSetter:
                                    Calculated Tool Length Z: {toffset:.4f}
                                    Setter Height: {p:.4f}
                                    Probed Position: {h:.4f}''')
            # report success
            return 1
        except Exception as e:
            return f'{e}'

    def probe_ts_z(self):
        try:
            # basic sanity checks
            if self.data_ts_max is None:
                return 'Missing toolsetter setting: data_ts_max'

            # probe Z
            # raise z clear

            cmdList = []
            cmdList.append('G49')
            cmdList.append('G91')
            cmdList.append(f'G38.2 Z-{self.data_ts_max} F{self.data_search_vel}')
            cmdList.append(f'G1 Z{self.data_latch_return_dist} F{self.data_rapid_vel}')
            cmdList.append(f'F{self.data_probe_vel}')
            cmdList.append(f'G38.2 Z-{self.data_latch_return_dist * 1.2}')
            cmdList.append(f'G1 Z{self.data_z_clearance} F{self.data_rapid_vel}')
            cmdList.append('G90')

            # call each command - if fail report the error and gcode command
            rtn = self.CALL_MDI_LIST(cmdList)
            if rtn != 1:
                return rtn
            h = STATUS.get_probed_position()[2]
            self.status_th = h
            self.add_history('Tool Setter height',"Z",0,0,0,0,0,0,0,0,h,0,0)

            # report success
            return 1
        except Exception as e:
            return f'{e}'

    # TOOL setter Diameter/height
    # returns 1 for success or a string error message for failure
    def probe_tool_z_diam(self):
        try:
            # probe tool height
            rtn = self.probe_tool_with_toolsetter()
            if rtn != 1:
                return f'failed: {rtn}'

            # confirm there is enough axis room to offset for diameters of tool and toolsetter
            xplimit = float(INFO.INI.find('AXIS_X','MAX_LIMIT'))
            xmlimit = float(INFO.INI.find('AXIS_X','MIN_LIMIT'))
            offset = (self.data_tool_diameter + self.data_ts_diam) * .5
            if (offset + self.data_ts_x) > xplimit:
                return 'cannot offset enough in + X for tool radius + toolsetter radius'
            elif (self.data_ts_x - (offset)) < xmlimit:
                return 'cannot offset enough in - X for tool radius + toolsetter radius'

            yplimit = float(INFO.INI.find('AXIS_Y','MAX_LIMIT'))
            ymlimit = float(INFO.INI.find('AXIS_Y','MIN_LIMIT'))
            if (offset + self.data_ts_y) > yplimit:
                return 'cannot offset enough in + Y for tool radius offset + toolsetter radius'
            elif (self.data_ts_y - (offset)) < ymlimit:
                return 'cannot offset enough in - Y for tool radius offset + toolsetter radius'

            # move X-  (1/2 tool diameter + xy_clearance)
            s = f"""G91
            G1 F{self.data_rapid_vel} X-{0.5 * self.data_ts_diam + self.data_xy_clearance}
            G90"""
            rtn = self.CALL_MDI_WAIT(s, self.timeout)
            if rtn != 1:
                return f'failed: {rtn}'

            rtn = self.z_clearance_down()
            if rtn != 1:
                return f'failed: {rtn}'

            rtn = self.lower_tool_depth()
            if rtn != 1:
                return f'lower tool depth failed: {rtn}'

            # Start xplus
            rtn = self.probe('xplus')
            if rtn != 1:
                return f'failed: {rtn}'

            # show X result
            a = STATUS.get_probed_position_with_offsets()
            xpres = float(a[0]) + 0.5 * self.data_probe_diam

            rtn = self.raise_tool_depth()
            if rtn != 1:
                return f'raise tool depth failed: {rtn}'

            # move Z to start point up
            rtn = self.z_clearance_up()
            if rtn != 1:
                return f'failed: {rtn}'

            # move to found point X
            s = f"G1 F{self.data_rapid_vel} X{xpres}"
            rtn = self.CALL_MDI_WAIT(s, self.timeout) 
            if rtn != 1:
                return f'failed: {rtn}'

            # move X+ (data_ts_diam +  xy_clearance)
            aa = self.data_ts_diam + self.data_xy_clearance
            s = f"""G91
            G1 X{aa}
            G90"""
            rtn = self.CALL_MDI_WAIT(s, self.timeout) 
            if rtn != 1:
                return f'failed: {rtn}'

            rtn = self.z_clearance_down()
            if rtn != 1:
                return f'failed: {rtn}'

            rtn = self.lower_tool_depth()
            if rtn != 1:
                return f'lower tool depth failed: {rtn}'

            # Start xminus
            rtn = self.probe('xminus')
            if rtn != 1:
                return f'failed: {rtn}'

            # show X result
            a = STATUS.get_probed_position_with_offsets()
            xmres = float(a[0]) - 0.5 * self.data_probe_diam
            self.length_x()
            xcres = 0.5 * (xpres + xmres)
            self.status_xc = xcres

            rtn = self.raise_tool_depth()
            if rtn != 1:
                return f'raise tool depth failed: {rtn}'

            # move Z to start point up
            rtn = self.z_clearance_up()
            if rtn != 1:
                return f'failed: {rtn}'

            # go to the new center of X
            s = f"G1 F{self.data_rapid_vel} X{xcres}"
            rtn = self.CALL_MDI_WAIT(s, self.timeout) 
            if rtn != 1:
                return f'failed: {rtn}'

            # move Y - data_ts_diam/2 - xy_clearance
            a = 0.5 * self.data_ts_diam + self.data_xy_clearance
            s = f"""G91
            G1 Y-{a}
            G90"""
            rtn = self.CALL_MDI_WAIT(s, self.timeout) 
            if rtn != 1:
                return f'failed: {rtn}'

            rtn = self.z_clearance_down()
            if rtn != 1:
                return f'failed: {rtn}'

            rtn = self.lower_tool_depth()
            if rtn != 1:
                return f'lower tool depth failed: {rtn}'

            # Start yplus
            rtn = self.probe('yplus')
            if rtn != 1:
                return f'failed: {rtn}'

            # show Y result
            a = STATUS.get_probed_position_with_offsets()
            ypres = float(a[1]) + 0.5 * self.data_probe_diam

            rtn = self.raise_tool_depth()
            if rtn != 1:
                return f'raise tool depth failed: {rtn}'

            # move Z to start point up
            if self.z_clearance_up() == -1:
                return

            # move to found point Y
            s = f"G1 Y{ypres}"
            rtn = self.CALL_MDI_WAIT(s, self.timeout) 
            if rtn != 1:
                return f'failed: {rtn}'

            # move Y + data_ts_diam +  xy_clearance
            aa = self.data_ts_diam + self.data_xy_clearance
            s = f"""G91
            G1 Y{aa}
            G90"""
            rtn = self.CALL_MDI_WAIT(s, self.timeout) 
            if rtn != 1:
                return f'failed: {rtn}'

            rtn = self.z_clearance_down()
            if rtn != 1:
                return f'failed: {rtn}'

            rtn = self.lower_tool_depth()
            if rtn != 1:
                return f'lower tool depth failed: {rtn}'

            # Start yminus
            rtn = self.probe('yminus')
            if rtn != 1:
                return f'failed: {rtn}'
            # show Y result
            a = STATUS.get_probed_position_with_offsets()
            ymres = float(a[1]) - 0.5 * self.data_probe_diam
            self.length_y()

            # find, show and move to found point
            ycres = 0.5 * (ypres + ymres)
            self.status_yc = ycres
            diam = self.data_probe_diam + (ymres - ypres - self.data_ts_diam)
            self.status_d = diam

            rtn = self.raise_tool_depth()
            if rtn != 1:
                return f'raise tool depth failed: {rtn}'

            # move Z to start point up
            rtn = self.z_clearance_up()
            if rtn != 1:
                return f'failed: {rtn}'

            tmpz = STATUS.stat.position[2] - self.data_z_clearance
            self.status_z = tmpz
            self.add_history('Tool diameter',"XcYcZD",0,xcres,0,0,0,ycres,0,0,tmpz,diam,0)
            # move to found point
            s = f"G1 Y{ycres}"
            rtn = self.CALL_MDI_WAIT(s, self.timeout) 
            if rtn != 1:
                return f'failed: {rtn}'
            # success
            return 1
        except Exception as e:
            return f'{e}'

    def probe_material_z(self):
        try:
            # basic sanity checks
            if self.data_ts_max is None:
                return'Missing toolsetter setting: data_ts_max'

            cmdList = []
            cmdList.append('G49')
            cmdList.append('G92.1')
            cmdList.append('G10 L20 P0  Z[#<_abs_z>]')
            cmdList.append('G91')
            cmdList.append(f'F {self.data_search_vel}')
            cmdList.append(f'G38.2 Z-{self.data_ts_max}')
            cmdList.append(f'G1 Z{self.data_latch_return_dist} F{self.data_rapid_vel}')
            cmdList.append(f'F{self.data_probe_vel}')
            cmdList.append(f'G38.2 Z-{self.data_latch_return_dist * 1.2}')
            cmdList.append(f'G1 Z{self.data_z_clearance} F{self.data_rapid_vel}')
            cmdList.append('G90')

            # call each command - if fail report the error and gcode command
            rtn = self.CALL_MDI_LIST(cmdList)
            if rtn != 1:
                return rtn
            h = STATUS.get_probed_position()[2]
            self.status_bh  = h
            self.add_history('Probe Material Top',"Z",0,0,0,0,0,0,0,0,h,0,0)
            # report success
            return 1
        except Exception as e:
            return f'{e}'

    ####################
    # Z rotation probing
    ####################
    # Front left corner
    def probe_angle_yp(self):
        method = 'probe_angle_yp:'
        autozero = self.allow_auto_zero
        self.allow_auto_zero = False
        # move Y -xy_clearance
        s = f"""G91
        G1 Y-{self.data_xy_clearance} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('yplus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show Y result
        a = STATUS.get_probed_position_with_offsets()
        self.status_yc = float(a[1]) + (self.cal_diameter / 2)
        # move X +edge_length
        s = f"""G91
        G1 X{self.data_side_edge_length} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('yplus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show Y result
        a = STATUS.get_probed_position_with_offsets()
        self.status_yp = float(a[1]) + (self.cal_diameter / 2)
        alfa = math.degrees(math.atan2(self.status_yp - self.status_yc, self.data_side_edge_length))
        self.add_history('Rotation YP ', "YcYpA", 0, 0, 0, 0, 0, self.status_yc, self.status_yp, 0, 0, 0, alfa)
        # move Z to start point
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        self.rotate_coord_system(alfa)
        self.allow_auto_zero = autozero
        return 1

    # Back right corner
    def probe_angle_ym(self):
        method = 'probe_angle_ym:'
        autozero = self.allow_auto_zero
        self.allow_auto_zero = False
        # move Y+ xy_clearance
        s = f"""G91
        G1 Y{self.data_xy_clearance} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('yminus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show Y result
        a = STATUS.get_probed_position_with_offsets()
        self.status_yc = float(a[1]) - (self.cal_diameter / 2)
        # move X- edge_length
        s = f"""G91
        G1 X-{self.data_side_edge_length} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('yminus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show Y result
        a = STATUS.get_probed_position_with_offsets()
        self.status_ym = float(a[1]) - (self.cal_diameter / 2)
        alfa = math.degrees(math.atan2(self.status_yc - self.status_ym, self.data_side_edge_length))
        self.add_history('Rotation YM ', "YmYcA", 0, 0, 0, 0, self.status_ym, self.status_yc, 0, 0, 0, 0, alfa)
        # move Z to start point
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        self.rotate_coord_system(alfa)
        self.allow_auto_zero = autozero
        return 1

    # Back left corner
    def probe_angle_xp(self):
        method = 'probe_angle_xp:'
        autozero = self.allow_auto_zero
        self.allow_auto_zero = False
        # move X- xy_clearance
        s = f"""G91
        G1 X-{self.data_xy_clearance} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('xplus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show X result
        a = STATUS.get_probed_position_with_offsets()
        self.status_xc = float(a[0]) + (self.cal_diameter / 2)
        # move Y- edge_length
        s = f"""G91
        G1 Y-{self.data_side_edge_length} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('xplus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show X result
        a = STATUS.get_probed_position_with_offsets()
        self.status_xp = float(a[0]) + (self.cal_diameter / 2)
        alfa = math.degrees(math.atan2(xcres - xpres, self.data_side_edge_length))
        self.add_history('Rotation XP', "XcXpA", 0, self.status_xc, self.status_xp, 0, 0, 0, 0, 0, 0, 0, alfa)
        # move Z to start point
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        self.rotate_coord_system(alfa)
        self.allow_auto_zero = autozero
        return 1

    # Front right corner
    def probe_angle_xm(self):
        method = 'probe_angle_xm:'
        autozero = self.allow_auto_zero
        self.allow_auto_zero = False
        # move to first probe position
        s = f"""G91
        G1 X{self.data_xy_clearance} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('xminus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show X result
        a = STATUS.get_probed_position_with_offsets()
        self.status_xc = float(a[0]) - (self.cal_diameter / 2)
        # move to second probe postion
        s = f"""G91
        G1 Y{self.data_side_edge_length} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('xminus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show X result
        a = STATUS.get_probed_position_with_offsets()
        self.status_xm = float(a[0]) - (self.cal_diameter / 2)
        alfa = math.degrees(math.atan2(self.status_xc - self.status_xm, self.data_side_edge_length))
        self.add_history('Rotation XM ', "XmXcA", self.status_xm, self.status_xc, 0, 0, 0, 0, 0, 0, 0, 0, alfa)
        # move Z to start point
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        self.rotate_coord_system(alfa)
        self.allow_auto_zero = autozero
        return 1

###################
#  Inside probing
###################
    def probe_xy_hole(self):
        method = 'probe_xy_hole:'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to probe X start position
        tmpx = self.data_side_edge_length - self.data_xy_clearance
        if tmpx > 0:
            s = f"""G91
            G1 X-{tmpx} F{self.data_rapid_vel}
            G90"""
            rtn = self.CALL_MDI_WAIT(s, self.timeout) 
            if rtn != 1:
                return f'{method} {rtn}'
        elif self.data_max_travel < self.data_side_edge_length:
                return f'{method} Max travel is less then hole radius while xy_clearance is too large for rapid  positioning'
        elif self.data_max_travel < (2 * self.data_side_edge_length - self.data_latch_return_dist):
                return f'{method} Max travel is less then hole diameter while xy_clearance is too large for rapid  positioning'
        # rough probe
        rtn = self.probe('xminus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show X result
        a = STATUS.get_probed_position_with_offsets()
        self.status_xm =  float(a[0]) - (self.cal_diameter / 2)
        # move to next probe position
        tmpx = (2 * self.data_side_edge_length) - self.data_latch_return_dist - self.data_xy_clearance
        if tmpx > 0:
            s = f"""G91
            G1 X{tmpx} F{self.data_rapid_vel}
            G90"""
            rtn = self.CALL_MDI_WAIT(s, self.timeout) 
            if rtn != 1:
                return f'{method} {rtn}'
        rtn = self.probe('xplus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show X result
        a = STATUS.get_probed_position_with_offsets()
        self.status_xp = float(a[0]) + (self.cal_diameter / 2)
        len_x = self.length_x()
        self.status_xc = (self.status_xm + self.status_xp) / 2
        # move X to new center
        s = f"""G90
        G1 X{xcres} F{self.data_rapid_vel}"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'

        # move to probe Y start position
        tmpy = self.data_side_edge_length - self.data_xy_clearance
        if tmpy > 0:
            s = f"""G91
            G1 Y-{tmpy} F{self.data_rapid_vel}
            G90"""
            rtn = self.CALL_MDI_WAIT(s, self.timeout) 
            if rtn != 1:
                return f'{method} {rtn}'
        rtn = self.probe('yminus')
        if rtn == -1: return f'{method}: {rtn}'
        # show Y result
        a = STATUS.get_probed_position_with_offsets()
        self.status_ym = float(a[1]) - (self.cal_diameter / 2)
        # move to next probe position
        tmpy = (2 * self.data_side_edge_length) - self.data_latch_return_dist - self.data_xy_clearance
        if tmpy > 0:
            s = f"""G91
            G1 Y{tmpy} F{self.data_rapid_vel}
            G90"""
            rtn = self.CALL_MDI_WAIT(s, self.timeout) 
            if rtn != 1:
                return f'{method} {rtn}'
        rtn = self.probe('yplus')
        if rtn != 1:
            return f'{method}: {rtn}'
        # show Y result
        a = STATUS.get_probed_position_with_offsets()
        self.status_yp = float(a[1]) + (self.cal_diameter / 2)
        len_y = self.length_y()
        # find, show and move to found  point
        self.status_yc = (self.status_ym + self.status_yp) / 2
        self.status_d = ((self.status_xp - self.status_xm) + (self.status_yp - self.status_ym)) / 2
        self.add_history('Inside Hole ', "XmXcXpLxYmYcYpLyD", self.status_xm, self.status_xc, self.status_xp, len_x, self.status_ym, self.status_yc, self.status_yp, len_y, 0, self.status_d, 0)
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to center
        s = f"G1 Y{self.status_yc} F{self.data_rapid_vel}"
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        self.set_zero("XY")
        return 1
        
    # Corners
    # Move Probe manual under corner 2-3 mm
    # Back right inside corner
    def probe_inside_xpyp(self):
        method = 'probe_inside_xpyp:'
        # move to XY start position
        s = f"""G91
        G1 X-{self.data_xy_clearance} Y-{self.data_side_edge_length} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('xplus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show X result
        a = STATUS.get_probed_position_with_offsets()
        self.status_xp = float(a[0]) + (self.cal_diameter / 2)
        len_x = self.length_x()
        # move to second XY start position
        ax = self.data_xy_clearance - self.data_latch_return_dist
        ay = self.data_side_edge_length - self.data_xy_clearance
        s = f"""G91
        G1 X-{ax} Y{ay} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('yplus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show Y result
        a = STATUS.get_probed_position_with_offsets()
        self.status_yp = float(a[1]) + (self.cal_diameter / 2)
        len_y = self.length_y()
        self.add_history('Inside XPYP ', "XpLxYpLy", 0, 0, self.status_xp, len_x, 0, 0, self.status_yp, len_y, 0, 0, 0)
        # move Z to start point
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found  point
        s = f"G1 X{self.status_xp} Y{self.status_yp} F{self.data_rapid_vel}"
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        self.set_zero("XY")
        return 1

    # Front right inside corner
    def probe_inside_xpym(self):
        method = 'probe_inside_xpym'
        # move to XY start position
        s = f"""G91
        G1 X-{self.data_xy_clearance} Y{self.data_side_edge_length} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('xplus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show X result
        a = STATUS.get_probed_position_with_offsets()
        self.status_xp = float(a[0]) + (self.cal_diameter / 2)
        len_x = self.length_x()
        # move to second XY start position
        ax = self.data_xy_clearance - self.data_latch_return_dist
        ay = self.data_side_edge_length - self.data_xy_clearance
        s = f"""G91
        G1 X-{ax} Y-{ay} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('yminus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show Y result
        a = STATUS.get_probed_position_with_offsets()
        self.status_ym = float(a[1]) - (self.cal_diameter / 2)
        len_y = self.length_y()
        self.add_history('Inside XPYM ', "XpLxYmLy", 0, 0, self.status_xp, len_x, self.status_ym, 0, 0, len_y, 0, 0, 0)
        # move Z to start point
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found  point
        s = f"G1 X{self.status_xp} Y{self.status_ym} F{self.data_rapid_vel}"
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        self.set_zero("XY")
        return 1

    # Back left inside corner
    def probe_inside_xmyp(self):
        method = 'probe_inside_xmyp:'
        # move to XY start position
        s = f"""G91
        G1 X{self.data_xy_clearance} Y-{self.data_side_edge_length} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('xminus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show X result
        a = STATUS.get_probed_position_with_offsets()
        self.status_xm = float(a[0]) - (self.cal_diameter / 2)
        len_x = self.length_x()
        # move to second XY start position
        ax = self.data_xy_clearance - self.data_latch_return_dist
        ay = self.data_side_edge_length - self.data_xy_clearance
        s = f"""G91
        G1 X{ax} Y{ay} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('yplus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show Y result
        a = STATUS.get_probed_position_with_offsets()
        self.status_yp = float(a[1]) + (self.cal_diameter / 2)
        len_y = self.length_y()
        self.add_history('Inside XMYP', "XmLxYpLy", self.status_xm, 0, 0, len_x, 0, 0, self.status_yp, len_y, 0, 0, 0)
        # move Z to start point
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found  point
        s = f"G1 X{self.status_xm} Y{self.status_yp} F{self.data_rapid_vel}"
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        self.set_zero("XY")
        return 1

    # Front left inside corner
    def probe_inside_xmym(self):
        method = 'probe_inside_xmym:'
        # move to XY start position
        s = f"""G91
        G1 X{self.data_xy_clearance} Y{self.data_side_edge_length} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('xminus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show X result
        a = STATUS.get_probed_position_with_offsets()
        self.status_xm = float(a[0]) - (self.cal_diameter / 2)
        len_x = self.length_x()
        # move to second XY start position
        ax = self.data_xy_clearance - self.data_latch_return_dist
        ay = self.data_side_edge_length - self.data_xy_clearance
        s = f"""G91
        G1 X{ax} Y-{ay} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('yminus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show Y result
        a = STATUS.get_probed_position_with_offsets()
        self.status_ym = float(a[1]) - (self.cal_diameter / 2)
        len_y = self.length_y()
        self.add_history('Inside XMYM', "XmLxYmLy", self.status_xm, 0, 0, len_x, self.status_ym, 0, 0, len_y, 0, 0, 0)
        # move Z to start point
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found  point
        s = f"G1 X{self.status_xm} Y{self.status_ym} F{self.data_rapid_vel}"
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        self.set_zero("XY")
        return 1

#################
# Outside probing
#################

    # Left outside edge, right inside edge
    def probe_xp(self):
        method = 'probe_xp:'
        # move to XY start point
        s = f"""G91
        G1 X-{self.data_xy_clearance} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('xplus')
        if rtn != 1:
            return f'{method} {rtn}'
        a = STATUS.get_probed_position_with_offsets()
        self.status_xp = float(a[0]) + (self.cal_diameter / 2)
        len_x = 0
        self.add_history('Outside XP ', "XpLx", 0, 0, self.status_xp, len_x, 0, 0, 0, 0, 0, 0, 0)
        # move Z to start point up
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found  point
        s = f"G1 X{self.status_xp} F{self.data_rapid_vel}"
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        self.set_zero("X")
        return 1

    # Front outside edge, back inside edge
    def probe_yp(self):
        method = 'probe_yp:'
        # move to XY start point
        s = f"""G91
        G1 Y-{self.data_xy_clearance} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('yplus')
        if rtn != 1:
            return f'{method} {rtn}'
        a = STATUS.get_probed_position_with_offsets()
        self.status_yp = float(a[1]) + (self.cal_diameter / 2)
        len_y = 0
        self.add_history('Outside YP ', "YpLy", 0, 0, 0, 0, 0, 0, self.status_yp, len_y, 0, 0, 0)
        # move Z to start point up
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found  point
        s = f"G1 Y{self.status_yp} F{self.data_rapid_vel}"
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        self.set_zero("Y")
        return 1

    # Right outside edge, left inside edge
    def probe_xm(self):
        method = 'probe_xm:'
        # move to XY start point
        s = f"""G91
        G1 X{self.data_xy_clearance} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('xminus')
        if rtn != 1:
            return f'{method} {rtn}'
        a = STATUS.get_probed_position_with_offsets()
        self.status_xm = float(a[0]) - (self.cal_diameter / 2)
        len_x = 0
        self.add_history('Outside XM ', "XmLx", self.status_xm, 0, 0, len_x, 0, 0, 0, 0, 0, 0, 0)
        # move Z to start point up
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found  point
        s = f"G1 X{self.status_xm} F{self.data_rapid_vel}"
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        self.set_zero("X")
        return 1

    # Back outside edge, front inside edge
    def probe_ym(self):
        method = 'probe_ym:'
        # move to XY start point
        s = f"""G91
        G1 Y{self.data_xy_clearance} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout)
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'failed: {rtn}'
        rtn = self.probe('yminus')
        if rtn != 1:
            return f'{method} {rtn}'
        a = STATUS.get_probed_position_with_offsets()
        self.status_ym = float(a[1]) - (self.cal_diameter / 2)
        len_y = 0
        self.add_history('Outside YM ', "YmLy", 0, 0, 0, 0, self.status_ym, 0, 0, len_y, 0, 0, 0)
        # move Z to start point up
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found  point
        s = f"G1 Y{self.status_ym} F{self.data_rapid_vel}"
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        self.set_zero("Y")
        return 1

    # Corners
    # Move Probe manual over corner 2-3 mm
    # Front left outside corner
    def probe_outside_xpyp(self):
        method = 'probe_outside_xpyp:'
        # move to first XY start point
        s = f"""G91
        G1 X-{self.data_xy_clearance} Y{self.data_side_edge_length} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('xplus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show X result
        a = STATUS.get_probed_position_with_offsets()
        self.status_xp = float(a[0]) + (self.cal_diameter / 2)
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to second XY start point
        ax = self.data_side_edge_length + self.data_latch_return_dist
        ay = self.data_side_edge_length + self.data_xy_clearance
        s = f"""G91
        G1 X{ax} Y-{ay} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('yplus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show Y result
        a = STATUS.get_probed_position_with_offsets()
        self.status_yp = float(a[1]) + (self.cal_diameter / 2)
        self.add_history('Outside XPYP ', "XpYp", 0, 0, self.status_xp, 0, 0, 0, self.status_yp, 0, 0, 0, 0)
        # move Z to start point up
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found  point
        s = f"G1 X{self.status_xp} Y{self.status_yp} F{self.data_rapid_vel}"
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        self.set_zero("XY")
        return 1

    # Back left outside corner
    def probe_outside_xpym(self):
        method = 'probe_outside_xpym:'
        # move to first XY start point
        s = f"""G91
        G1 X-{self.data_xy_clearance} Y-{self.data_side_edge_length} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('xplus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show X result
        a = STATUS.get_probed_position_with_offsets()
        self.status_xp = float(a[0]) + (self.cal_diameter / 2)
        # move Z to start point up
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to second XY start point
        ax = self.data_side_edge_length + self.data_latch_return_dist
        ay = self.data_side_edge_length + self.data_xy_clearance
        s = f"""G91
        G1 X{ax} Y{ay} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('yminus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show Y result
        a = STATUS.get_probed_position_with_offsets()
        self.status_ym = float(a[1]) - (self.cal_diameter / 2)
        self.add_history('Outside XPYM ', "XpYm", 0, 0, self.status_xp, 0, self.status_ym, 0, 0, 0, 0, 0, 0)
        # move Z to start point up
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found point
        s = f"G1 X{self.status_xp} Y{self.status_ym} F{self.data_rapid_vel}"
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        self.set_zero("XY")
        return 1

    # Front right outside corner
    def probe_outside_xmyp(self):
        method = 'probe_outside_xmyp:'
        # move to first XY start point
        s = f"""G91
        G1 X{self.data_xy_clearance} Y{self.data_side_edge_length} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('xminus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show X result
        a = STATUS.get_probed_position_with_offsets()
        self.status_xm = float(a[0]) - (self.cal_diameter / 2)
        # move Z to start point up
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to second XY start point
        ax = self.data_side_edge_length + self.data_latch_return_dist
        ay = self.data_side_edge_length + self.data_xy_clearance
        s = f"""G91
        G1 X-{ax} Y-{ay} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('yplus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show Y result
        a = STATUS.get_probed_position_with_offsets()
        self.status_yp = float(a[1]) + (self.cal_diameter / 2)
        self.add_history('Outside XMYP ', "XmYp", self.status_xm, 0, 0, 0, 0, 0, self.status_yp, 0, 0, 0, 0)
        # move Z to start point up
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found  point
        s = f"G1 X{self.status_xm} Y{self.status_yp} F{self.data_rapid_vel}"
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        self.set_zero("XY")
        return 1

    # Back right outside corner
    def probe_outside_xmym(self):
        method = 'probe_outside_xmym:'
        # move to first XY start point
        s = f"""G91
        G1 X{self.data_xy_clearance} Y-{self.data_side_edge_length} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('xminus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show X result
        a = STATUS.get_probed_position_with_offsets()
        self.status_xm = float(a[0]) - (self.cal_diameter / 2)
        # move Z to start point up
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to second XY start point
        ax = self.data_side_edge_length + self.data_latch_return_dist
        ay = self.data_side_edge_length + self.data_xy_clearance
        s = f"""G91
        G1 X-{ax} Y{ay} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('yminus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show Y result
        a = STATUS.get_probed_position_with_offsets()
        self.status_ym = float(a[1]) - (self.cal_diameter / 2)
        self.add_history('Outside XMYM ', "XmYm", self.status_xm, 0, 0, 0, self.status_ym, 0, 0, 0, 0, 0, 0)
        # move Z to start point up
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found  point
        s = f"G1 X{self.status_xm} Y{self.status_ym} F{self.data_rapid_vel}"
        rtn = self.CALL_MDI_WAIT(s, self.timeout)
        if rtn != 1:
            return f'{method} {rtn}'
        self.set_zero("XY")
        return 1

    def probe_outside_xy_boss(self, x, y):
        self.data_side_edge_length = x
        error = self.probe_outside_length_x()
        if error != 1: return error
        self.data_side_edge_length = y
        error = self.probe_outside_length_y()
        return error

#######################
# Straight down probing
#######################
    # Probe Z Minus direction and set Z0 in current WCO
    # End at Z_clearance above workpiece
    def probe_down(self):
        method = 'probe_down:'
        ACTION.CALL_MDI("G91")
        s = f"G38.2 Z-{self.data_max_z} F{self.data_search_vel}"
        rtn = self.CALL_MDI_WAIT(s, self.timeout)
        if rtn != 1:
            return f'{method} fast probe failed: {rtn}'
        s = f"G1 Z{self.data_latch_return_dist} F{self.data_rapid_vel}"
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} latch return failed: {rtn}'
        ACTION.CALL_MDI("G4 P0.5")
        s = f"G38.2 Z-{1.2 * self.data_latch_return_dist} F{self.data_probe_vel}"
        rtn = self.CALL_MDI_WAIT(s, self.timeout)
        if rtn != 1:
            return f'{method} slow probe failed: {rtn}'
        a = STATUS.get_probed_position_with_offsets()
        self.status_z = float(a[2])
        self.add_history('Straight Down ', "Z", 0, 0, 0, 0, 0, 0, 0, 0, a[2], 0, 0)
        self.set_zero("Z")
        s = f"""G91
        G1 Z{self.data_z_clearance} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout)
        if rtn != 1:
            return f'{method} move to Z clearence failed: {rtn}'
        return 1

########
# Length
########
    def probe_outside_length_x(self):
        method = 'probe_outside_length_x:'
        # move X to probe start position
        s = f"""G91
        G1 X-{self.data_side_edge_length + self.data_xy_clearance} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('xplus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show X result
        a = STATUS.get_probed_position_with_offsets()
        self.status_xp = float(a[0]) + (self.cal_diameter / 2)
        # move Z to start point up
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to second probe start position
        tmpx = (2 * self.data_side_edge_length) + self.data_xy_clearance + self.data_latch_return_dist
        s = f"""G91
        G1 X{tmpx} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('xminus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show X result
        a = STATUS.get_probed_position_with_offsets()
        self.status_xm = float(a[0]) - (self.cal_diameter / 2)
        self.status_xc = (self.status_xp + self.status_xm) / 2
        len_x = self.length_x()
        self.add_history('Outside Length X ', "XmXcXpLx", self.status_xm, self.status_xc, self.status_xp, len_x, 0,0,0,0,0,0,0)
        # move Z to start point up
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # go to the new center of X
        s = f"G1 X{self.status_xc} F{self.data_rapid_vel}"
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        self.set_zero("X")
        return 1

    def probe_outside_length_y(self):
        method = 'probe_outside_length_y:'
        # move Y to probe start position
        s = f"""G91
        G1 Y-{self.data_side_edge_length + self.data_xy_clearance} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('yplus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show Y result
        a = STATUS.get_probed_position_with_offsets()
        self.status_yp = float(a[1]) + (self.cal_diameter / 2)
        # move Z to start point up
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to second probe start position
        tmpy = (2 * self.data_side_edge_length) + self.data_xy_clearance + self.data_latch_return_dist
        s = f"""G91
        G1 Y{tmpy} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('yminus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show Y result
        a = STATUS.get_probed_position_with_offsets()
        self.status_ym = float(a[1]) - (self.cal_diameter / 2)
        len_y = self.length_y()
        # find, show and move to found  point
        self.status_yc = (self.status_yp + self.status_ym) / 2
        self.add_history('Outside Length Y ', "YmYcYpLy", 0, 0, 0, 0, self.status_ym, self.status_yc, self.status_yp, len_y, 0, 0, 0)
        # move Z to start point up
        rtn =  self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found  point
        s = f"G1 Y{self.status_yc} F{self.data_rapid_vel}"
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        self.set_zero("Y")
        return 1

    def probe_inside_length_x(self):
        method = 'probe_inside_length_x:'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to probe start position
        s = f"""G91
        G1 X-{self.data_side_edge_length - self.data_xy_clearance} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('xminus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show X result
        a = STATUS.get_probed_position_with_offsets()
        self.status_xm = float(a[0]) - (self.cal_diameter / 2)
        # move to second probe position
        tmpx = (2 * self.data_side_edge_length) - self.data_latch_return_dist - self.data_xy_clearance
        s = f"""G91
        G1 X{tmpx} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('xplus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show X result
        a = STATUS.get_probed_position_with_offsets()
        self.status_xp = float(a[0]) + (self.cal_diameter / 2)
        len_x = self.length_x()
        self.status_xc = (self.status_xm + self.status_xp) / 2
        self.add_history('Inside Length X ', "XmXcXpLx", self.status_xm, self.status_xc, self.status_xp, len_x, 0,0,0,0,0,0,0)
        # move Z to start point
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # move X to new center
        s = f"""G1 X{self.status_xc} F{self.data_rapid_vel}"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        self.set_zero("X")
        return 1

    def probe_inside_length_y(self):
        method = 'probe_inside_length_y:'
        rtn = self.z_clearance_down()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to probe start position
        s = f"""G91
        G1 Y-{self.data_side_edge_length - self.data_xy_clearance} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('yminus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show Y result
        a = STATUS.get_probed_position_with_offsets()
        self.status_ym = float(a[1]) - (self.cal_diameter / 2)
        # move to second probe position
        tmpy = (2 * self.data_side_edge_length) - self.data_latch_return_dist - self.data_xy_clearance
        s = f"""G91
        G1 Y{tmpy} F{self.data_rapid_vel}
        G90"""
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.probe('yplus')
        if rtn != 1:
            return f'{method} {rtn}'
        # show Y result
        a = STATUS.get_probed_position_with_offsets()
        self.status_yp = float(a[1]) + (self.cal_diameter / 2)
        len_y = self.length_y()
        # find, show and move to found  point
        self.status_yc = (self.status_ym + self.status_yp) / 2
        self.add_history('Inside Length Y ', "YmYcYpLy", 0, 0, 0, 0, self.status_ym, self.status_yc, self.status_yp, len_y, 0, 0, 0)
        # move Z to start point
        rtn = self.z_clearance_up()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to center
        s = f"G1 Y{self.status_yc} F{self.data_rapid_vel}"
        rtn = self.CALL_MDI_WAIT(s, self.timeout) 
        if rtn != 1:
            return f'{method} {rtn}'
        self.set_zero("Y")
        return 1

    def probe_round_boss(self):
        if self.data_diameter_hint <= 0:
            return 'Boss diameter hint must be larger than 0'
#        self.data_side_edge_length = self.data_diameter_hint / 2
        x = y = self.data_diameter_hint / 2
        error = self.probe_outside_xy_boss(x, y)
        if error != 1: return error
        self.status_d = (self.status_lx + self.status_ly) / 2
        return 1

    def probe_round_pocket(self):
        if self.data_diameter_hint <= 0:
            return 'Pocket diameter hint must be larger than 0'
        if self.data_probe_diam >= self.data_diameter_hint:
            return 'Probe diameter too large for hole diameter hint'
        self.data_side_edge_length = self.data_diameter_hint / 2
        error = self.probe_inside_length_x()
        if error != 1: return error
        self.error = self.probe_inside_length_y()
        if error != 1: return error
        self.status_d = (self.status_lx + self.status_ly) / 2
        return 1

    def probe_rectangular_boss(self):
        if self.data_y_hint_bp <= 0:
            return 'Y length hint must be larger than 0'
        if self.data_x_hint_bp <= 0:
            return 'X length hint must be larger than 0'
#        self.data_side_edge_length = self.data_x_hint_bp / 2
        x = self.data_x_hint_bp / 2
#        error = self.probe_outside_length_x()
#        if error != 1: return error
#        self.data_side_edge_length = self.data_y_hint_bp / 2
        y = self.data_y_hint_bp / 2
#        error = self.probe_outside_length_y()
        error = self.probe_outside_xy_boss(x,y)
        return error

    def probe_rectangular_pocket(self):
        if self.data_y_hint_bp <= 0:
            return 'Y length hint must be larger than 0'
        if self.data_x_hint_bp <= 0:
            return 'X length hint must be larger than 0'
        if self.data_probe_diam >= self.data_y_hint_bp / 2:
            return 'Probe diameter too large for Y length hint'
        if self.data_probe_diam >= self.data_x_hint_bp / 2:
            return 'Probe diameter too large for X length hint'
        self.data_side_edge_length = self.data_x_hint_bp / 2
        error = self.probe_inside_length_x()
        if error != 1: return error
        self.data_side_edge_length = self.data_y_hint_bp / 2
        error = self.probe_inside_length_y()
        return error

    def probe_ridge_x(self):
        if self.data_x_hint_rv <= 0:
            return 'X length hint must be larger than 0'
        self.data_side_edge_length = self.data_x_hint_rv / 2
        error = self.probe_outside_length_x()
        return error

    def probe_ridge_y(self):
        if self.data_y_hint_rv <= 0:
            return 'Y length hint must be larger than 0'
        self.data_side_edge_length = self.data_y_hint_rv / 2
        error = self.probe_outside_length_y()
        return error

    def probe_valley_x(self):
        if self.data_x_hint_rv <= 0:
            return 'X length hint must be larger than 0'
        if self.data_probe_diam >= self.data_x_hint_rv / 2:
            return 'Probe diameter too large for X length hint'
        self.data_side_edge_length = self.data_x_hint_rv / 2
        error = self.probe_inside_length_x()
        return error

    def probe_valley_y(self):
        if self.data_y_hint_rv <= 0:
            return 'Y length hint must be larger than 0'
        if self.data_probe_diam >= self.data_y_hint_rv / 2:
            return 'Probe diameter too large for Y length hint'
        self.data_side_edge_length = self.data_y_hint_rv / 2
        error = self.probe_inside_length_y()
        return error

    def probe_cal_round_pocket(self):
        # reset calibration offset to 0
        self.cal_diameter = self.data_probe_diam
        if self.data_cal_diameter <= 0:
            return 'Calibration diameter must be larger than 0'
        if self.data_probe_diam >= self.data_cal_diameter:
            return 'Probe diameter too large for cal diameter'
        self.data_side_edge_length = self.data_cal_diameter / 2
        error = self.probe_xy_hole()
        if error != 1: return error
        # repeat but this time start from calculated center
        error = self.probe_xy_hole()
        if error != 1: return error
        self.status_offset = self.get_new_offset('r')
        self.cal_diameter = self.data_probe_diam + self.status_offset
        self.status_d = self.data_cal_diameter
        return 1

    def probe_cal_square_pocket(self):
        # reset calibration offset to 0
        self.cal_diameter = self.data_probe_diam
        if self.data_cal_x_width <= 0:
            return 'Calibration X width must be larger than 0'
        if self.data_cal_y_width <= 0:
            return 'Calibration Y width must be larger than 0'
        self.data_side_edge_length = self.data_cal_x_width / 2
        error = self.probe_inside_length_x()
        if error != 1: return error
        self.data_side_edge_length = self.data_cal_y_width / 2
        error = self.probe_inside_length_y()
        if error != 1: return error
        self.status_offset = self.get_new_offset('s')
        self.cal_diameter = self.data_probe_diam + self.status_offset
        self.status_lx = self.data_cal_x_width
        self.status_ly = self.data_cal_y_width
        return 1

    def probe_cal_round_boss(self):
        # reset calibration offset to 0
        self.cal_diameter = self.data_probe_diam
        if self.data_cal_diameter <= 0:
            return 'Calibration diameter must be larger than 0'
        x = y = self.data_cal_diameter / 2
        error = self.probe_outside_xy_boss(x, y)
        if error != 1: return error
        # repeat but this time start from calculated center
        error = self.probe_outside_xy_boss(x, y)
        if error != 1: return error
        self.status_offset = self.get_new_offset('r')
        self.cal_diameter = self.data_probe_diam + self.status_offset
        self.status_d = self.data_cal_diameter
        return 1

    def probe_cal_square_boss(self):
        # reset calibration offset to 0
        self.cal_diameter = self.data_probe_diam
        if self.data_cal_x_width <= 0:
            return 'Calibration X width must be larger than 0'
        if self.data_cal_y_width <= 0:
            return 'Calibration Y width must be larger than 0'
        self.data_side_edge_length = self.data_cal_x_width / 2
        error = self.probe_outside_length_x()
        if error != 1: return error
        self.data_side_edge_length = self.data_cal_y_width / 2
        error = self.probe_outside_length_y()
        if error != 1: return error
        self.status_offset = self.get_new_offset('s')
        self.cal_diameter = self.data_probe_diam + self.status_offset
        self.status_lx = self.data_cal_x_width
        self.status_ly = self.data_cal_y_width
        return 1

    def get_new_offset(self, shape):
        if shape == 'r':
            base_x = base_y = self.data_cal_diameter
        elif shape == 's':
            base_x = self.data_cal_x_width
            base_y = self.data_cal_y_width
        else: return 0
        xcal_error = self.status_lx - base_x
        newx_offset = self.data_cal_offset + xcal_error
        ycal_error = self.status_ly - base_y
        newy_offset = self.data_cal_offset + ycal_error
        new_cal_avg = (xcal_error + ycal_error) / 2
        if self.cal_x_error is True: return xcal_error
        elif self.cal_y_error is True: return ycal_error
        else: return new_cal_avg

