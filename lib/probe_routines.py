#!/usr/bin/env python3
# QtDragon - material probing routines
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
import math
from qtvcp.core import Status, Info

STATUS = Status()
INFO = Info()


class ProbeRoutines():
    def __init__(self):
        self.timeout = 30
        self.tpl = '.3f' if INFO.MACHINE_IS_METRIC else '.4f'
##################
# Helper Functions
##################
    def set_timeout(self, time):
        self.timeout = time

    def get_current_position(self):
        xyz = []
        self.stat.poll()
        pos = self.stat.actual_position
        off = self.stat.g5x_offset
        tlo = self.stat.tool_offset
        for i in range(3):
            xyz.append(pos[i] - off[i] - tlo[i])
        return xyz

    def z_clearance_up(self):
        z_stack = self.parms['z_clearance'] + self.parms['probe_diam'] + self.parms['extra_depth']
        rtn = self.CALL_MDI_WAIT(f"G91 G1 Z{z_stack} F{self.parms['rapid_vel']}")
        if rtn != 1: return rtn
        return 1

    def z_clearance_down(self):
        z_stack = self.parms['z_clearance'] + self.parms['probe_diam']  + self.parms['extra_depth']
        rtn = self.CALL_MDI_WAIT(f"G91 G1 Z-{z_stack} F{self.parms['rapid_vel']}")
        if rtn != 1: return rtn
        return 1

    def length_x(self):
        if self.status['xp'] is None: self.status['xp'] = 0
        if self.status['xm'] is None: self.status['xm'] = 0
        if self.status['xp'] == 0 or self.status['xm'] == 0: return 0
        self.status['lx'] = abs(self.status['xm'] - self.status['xp'])
        return self.status['lx']

    def length_y(self):
        if self.status['yp'] is None: self.status['yp'] = 0
        if self.status['ym'] is None: self.status['ym'] = 0
        if self.status['yp'] == 0 or self.status['ym'] == 0: return 0
        self.status['ly'] = abs(self.status['ym'] - self.status['yp'])
        return self.status['ly']

    def set_zero(self, s):
        if self.allow_auto_zero is True:
            c = "G10 L20 P0"
            if "X" in s:
                c += f" X{self.parms['adj_x']}"
            if "Y" in s:
                c += f" Y{self.parms['adj_y']}"
            if "Z" in s:
                c += f" Z{self.parms['adj_z']}"
            self.CALL_MDI_WAIT(c)

    def rotate_coord_system(self, a=0.):
        self.status['a'] = a
        if self.allow_auto_skew is True:
            s = "G10 L2 P0"
            if self.allow_auto_zero is True:
                s += f" X{self.parms['adj_x']}"
                s += f" Y{self.parms['adj_y']}"
            else:
                self.stat.poll()
                x = self.stat.position[0]
                y = self.stat.position[1]
                s += f" X{x}"
                s += f" Y{y}"
            s +=  f" R{a}"
            self.CALL_MDI_WAIT(s)

    def add_history(self, *args):
        c = args[0]
        for arg in args[1:]:
            if self.status[arg] is not None:
                c += f' {arg}:{self.status[arg]:{self.tpl}}'
        self.history_log = c

    def add_history_xxx(self, *args):
        if len(args) == 13:
            c = args[0]
            _list = ['Xm', 'Xc', 'Xp', 'Lx', 'Ym', 'Yc', 'Yp', 'Ly', 'Z', 'D', 'A']
            for i in range(0, len(_list)):
                if _list[i] in args[1]:
                    c += f' {_list[i]}{args[i+2]:{self.tpl}}'
            self.history_log = c
        else:
            # should be a single string
            self.history_log = args[0]

    def probe(self, name):
        if name == "xm" or name == "ym" :
            travel = 0 - self.parms['max_travel']
            radius = 0 - self.probe_radius
            retract = self.parms['retract']
        elif name == "xp" or name == "yp":
            travel = self.parms['max_travel']
            radius = self.probe_radius
            retract = 0 - self.parms['retract']
        else:
            return 'invalid probe name'
        axis = name[0].upper()
        # begin probe to edge
        rtn = self.CALL_MDI_WAIT(f"G91 G38.2 {axis}{travel} F{self.parms['search_vel']}")
        if rtn != 1: return rtn
        rtn = self.CALL_MDI_WAIT(f"G1 {axis}{retract} F{self.parms['rapid_vel']}")
        if rtn != 1: return rtn
        rtn = self.CALL_MDI_WAIT("G4 P0.5")
        rtn = self.CALL_MDI_WAIT(f"G38.2 {axis}{(-1.2 * retract):{self.tpl}} F{self.parms['probe_vel']}")
        if rtn != 1: return rtn
        rtn = self.CALL_MDI_WAIT(f"G1 {axis}{retract} F{self.parms['rapid_vel']}")
        if rtn != 1: return rtn
        # get probed result
        idx = 0 if axis == 'X' else 1
        a = STATUS.get_probed_position_with_offsets()
        self.status[name] = float(a[idx]) + radius
        return 1

    ####################
    # Z rotation probing
    ####################
    # Front left corner
    def probe_angle_yp(self):
        method = 'probe_angle_yp:'
        autozero = self.allow_auto_zero
        self.allow_auto_zero = False
        self.commands.append(f"G91 G1 Y-{self.parms['stepoff']} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'yp'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        y1 = self.status['yp']
        self.commands.append(f"G91 G1 X{self.parms['edge_width']} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'yp'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        y2 = self.status['yp']
        self.status['delta'] = y2 - y1
        alfa = math.degrees(math.atan2(y2 - y1, self.parms['edge_width']))
        self.rotate_coord_system(alfa)
        self.allow_auto_zero = autozero
        self.add_history(method, 'delta', 'a')
        return 1

    # Back right corner
    def probe_angle_ym(self):
        method = 'probe_angle_ym:'
        autozero = self.allow_auto_zero
        self.allow_auto_zero = False
        self.commands.append(f"G91 G1 Y{self.parms['stepoff']} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'ym'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        y1 = self.status['ym']
        self.commands.append(f"G91 G1 X-{self.parms['edge_width']} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'ym'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        y2 = self.status['ym']
        self.status['delta'] = y2 - y1
        alfa = math.degrees(math.atan2(y1 - y2, self.parms['edge_width']))
        self.rotate_coord_system(alfa)
        self.allow_auto_zero = autozero
        self.add_history(method, 'delta', 'a')
        return 1

    # Back left corner
    def probe_angle_xp(self):
        method = 'probe_angle_xp:'
        autozero = self.allow_auto_zero
        self.allow_auto_zero = False
        self.commands.append(f"G91 G1 X-{self.parms['stepoff']} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'xp'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        x1 = self.status['xp']
        self.commands.append(f"G91 G1 Y-{self.parms['edge_width']} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'xp'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        x2 = self.status['xp']
        self.status['delta'] = x2 - x1
        alfa = math.degrees(math.atan2(x2 - x1, self.parms['edge_width']))
        self.rotate_coord_system(alfa)
        self.allow_auto_zero = autozero
        self.add_history(method, 'delta', 'a')
        return 1

    # Front right corner
    def probe_angle_xm(self):
        method = 'probe_angle_xm:'
        autozero = self.allow_auto_zero
        self.allow_auto_zero = False
        self.commands.append(f"G91 G1 X{self.parms['stepoff']} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'xm'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        x1 = self.status['xm']
        self.commands.append(f"G91 G1 Y{self.parms['edge_width']} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'xm'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        x2 = self.status['xm']
        self.status['delta'] = x2 - x1
        alfa = math.degrees(math.atan2(x1 - x2, self.parms['edge_width']))
        self.rotate_coord_system(alfa)
        self.allow_auto_zero = autozero
        self.add_history(method, 'delta', 'a')
        return 1
        
################
# Inside Corners
################
    # Back right inside corner
    def probe_inside_xpyp(self):
        method = 'probe_inside_xpyp:'
        pos = self.get_current_position()
        x2 = pos[0] - self.parms['xy_clearance']
        y2 = pos[1] - self.parms['stepoff']
        self.commands.append(f"G91 G1 X-{self.parms['stepoff']} Y-{self.parms['xy_clearance']} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'xp'))
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        self.commands.append(f"G90 G1 X{x2:{self.tpl}} Y{y2:{self.tpl}} F{self.parms['rapid_vel']}")
        self.commands.append((self.probe, 'yp'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        rtn = self.CALL_MDI_WAIT(f"G90 G1 X{self.status['xp']:{self.tpl}} Y{self.status['yp']:{self.tpl}} F{self.parms['rapid_vel']}")
        if rtn != 1:
            return f'{method} {rtn}'
        self.add_history(method, 'xp', 'yp')
        self.set_zero("XY")
        return 1

    # Front right inside corner
    def probe_inside_xpym(self):
        method = 'probe_inside_xpym'
        pos = self.get_current_position()
        x2 = pos[0] - self.parms['xy_clearance']
        y2 = pos[1] + self.parms['stepoff']
        self.commands.append(f"G91 G1 X-{self.parms['stepoff']} Y{self.parms['xy_clearance']} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'xp'))
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        self.commands.append(f"G90 G1 X{x2:{self.tpl}} Y{y2:{self.tpl}} F{self.parms['rapid_vel']}")
        self.commands.append((self.probe, 'ym'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        # move Z to found point
        rtn = self.CALL_MDI_WAIT(f"G90 G1 X{self.status['xp']:{self.tpl}} Y{self.status['ym']:{self.tpl}} F{self.parms['rapid_vel']}")
        if rtn != 1:
            return f'{method} {rtn}'
        self.add_history(method, 'xp', 'ym')
        self.set_zero("XY")
        return 1

    # Back left inside corner
    def probe_inside_xmyp(self):
        method = 'probe_inside_xmyp:'
        pos = self.get_current_position()
        x2 = pos[0] + self.parms['xy_clearance']
        y2 = pos[1] - self.parms['stepoff']
        self.commands.append(f"G91 G1 X{self.parms['stepoff']} Y-{self.parms['xy_clearance']} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'xm'))
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        self.commands.append(f"G90 G1 X{x2:{self.tpl}} Y{y2:{self.tpl}} F{self.parms['rapid_vel']}")
        self.commands.append((self.probe, 'yp'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found  point
        rtn = self.CALL_MDI_WAIT(f"G90 G1 X{self.status['xm']:{self.tpl}} Y{self.status['yp']:{self.tpl}} F{self.parms['rapid_vel']}")
        if rtn != 1:
            return f'{method} {rtn}'
        self.add_history(method, 'xm', 'yp')
        self.set_zero("XY")
        return 1

    # Front left inside corner
    def probe_inside_xmym(self):
        method = 'probe_inside_xmym:'
        pos = self.get_current_position()
        x2 = pos[0] + self.parms['xy_clearance']
        y2 = pos[1] + self.parms['stepoff']
        self.commands.append(f"G91 G1 X{self.parms['stepoff']} Y{self.parms['xy_clearance']} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'xm'))
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        self.commands.append(f"G90 G1 X{x2:{self.tpl}} Y{y2:{self.tpl}} F{self.parms['rapid_vel']}")
        self.commands.append((self.probe, 'ym'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found  point
        rtn = self.CALL_MDI_WAIT(f"G90 G1 X{self.status['xm']:{self.tpl}} Y{self.status['ym']:{self.tpl}} F{self.parms['rapid_vel']}")
        if rtn != 1:
            return f'{method} {rtn}'
        self.add_history(method, 'xm', 'ym')
        self.set_zero("XY")
        return 1

##############
# Edge probing
##############
    # Left outside edge, right inside edge
    def probe_xp(self):
        method = 'probe_xp:'
        self.commands.append(f"G91 G1 X-{self.parms['stepoff']} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'xp'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found  point
        rtn = self.CALL_MDI_WAIT(f"G90 G1 X{self.status['xp']} F{self.parms['rapid_vel']}")
        if rtn != 1:
            return f'{method} {rtn}'
        self.add_history(method, 'xp')
        self.set_zero("X")
        return 1

    # Front outside edge, back inside edge
    def probe_yp(self):
        method = 'probe_yp:'
        self.commands.append(f"G91 G1 Y-{self.parms['stepoff']} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'yp'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found  point
        rtn = self.CALL_MDI_WAIT(f"G90 G1 Y{self.status['yp']} F{self.parms['rapid_vel']}")
        if rtn != 1:
            return f'{method} {rtn}'
        self.add_history(method, 'yp')
        self.set_zero("Y")
        return 1

    # Right outside edge, left inside edge
    def probe_xm(self):
        method = 'probe_xm:'
        self.commands.append(f"G91 G1 X{self.parms['stepoff']} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'xm'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found  point
        rtn = self.CALL_MDI_WAIT(f"G90 G1 X{self.status['xm']} F{self.parms['rapid_vel']}")
        if rtn != 1:
            return f'{method} {rtn}'
        self.add_history(method, 'xm')
        self.set_zero("X")
        return 1

    # Back outside edge, front inside edge
    def probe_ym(self):
        method = 'probe_ym:'
        self.commands.append(f"G91 G1 Y{self.parms['stepoff']} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'ym'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found  point
        rtn = self.CALL_MDI_WAIT(f"G90 G1 Y{self.status['ym']} F{self.parms['rapid_vel']}")
        if rtn != 1:
            return f'{method} {rtn}'
        self.add_history(method, 'ym')
        self.set_zero("Y")
        return 1

#################
# Outside Corners
#################
    # Front left outside corner
    def probe_outside_xpyp(self):
        method = 'probe_outside_xpyp:'
        pos = self.get_current_position()
        x2 = pos[0] + self.parms['xy_clearance']
        y2 = pos[1] - self.parms['stepoff']
        self.commands.append(f"G91 G1 X-{self.parms['stepoff']} Y{self.parms['xy_clearance']} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'xp'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        self.commands.append(f"G90 G1 X{x2:{self.tpl}} Y{y2:{self.tpl}} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'yp'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found  point
        rtn = self.CALL_MDI_WAIT(f"G90 G1 X{self.status['xp']:{self.tpl}} Y{self.status['yp']:{self.tpl}} F{self.parms['rapid_vel']}")
        if rtn != 1:
            return f'{method} {rtn}'
        self.add_history(method, 'xp', 'yp')
        self.set_zero("XY")
        return 1

    # Back left outside corner
    def probe_outside_xpym(self):
        method = 'probe_outside_xpym:'
        pos = self.get_current_position()
        x2 = pos[0] + self.parms['xy_clearance']
        y2 = pos[1] + self.parms['stepoff']
        self.commands.append(f"G91 G1 X-{self.parms['stepoff']} Y-{self.parms['xy_clearance']} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'xp'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        self.commands.append(f"G90 G1 X{x2:{self.tpl}} Y{y2:{self.tpl}} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'ym'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found  point
        rtn = self.CALL_MDI_WAIT(f"G90 G1 X{self.status['xp']:{self.tpl}} Y{self.status['ym']:{self.tpl}} F{self.parms['rapid_vel']}")
        if rtn != 1:
            return f'{method} {rtn}'
        self.add_history(method, 'xp', 'ym')
        self.set_zero("XY")
        return 1

    # Front right outside corner
    def probe_outside_xmyp(self):
        method = 'probe_outside_xmyp:'
        pos = self.get_current_position()
        x2 = pos[0] - self.parms['xy_clearance']
        y2 = pos[1] - self.parms['stepoff']
        self.commands.append(f"G91 G1 X{self.parms['stepoff']} y{self.parms['xy_clearance']} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'xm'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        self.commands.append(f"G90 G1 X{x2:{self.tpl}} Y{y2:{self.tpl}} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'yp'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found  point
        rtn = self.CALL_MDI_WAIT(f"G90 G1 X{self.status['xm']:{self.tpl}} Y{self.status['yp']:{self.tpl}} F{self.parms['rapid_vel']}") 
        if rtn != 1:
            return f'{method} {rtn}'
        self.add_history(method, 'xm', 'yp')
        self.set_zero("XY")
        return 1

    # Back right outside corner
    def probe_outside_xmym(self):
        method = 'probe_outside_xmym:'
        pos = self.get_current_position()
        x2 = pos[0] - self.parms['xy_clearance']
        y2 = pos[1] + self.parms['stepoff']
        self.commands.append(f"G91 G1 X{self.parms['stepoff']} y-{self.parms['xy_clearance']} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'xm'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        self.commands.append(f"G90 G1 X{x2:{self.tpl}} Y{y2:{self.tpl}} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'ym'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        # move to found  point
        s = f"G90 G1 X{self.status['xm']:{self.tpl}} Y{self.status['ym']:{self.tpl}} F{self.parms['rapid_vel']}"
        rtn = self.CALL_MDI_WAIT(s)
        if rtn != 1:
            return f'{method} {rtn}'
        self.add_history(method, 'xm', 'ym')
        self.set_zero("XY")
        return 1

#######################
# Straight down probing
#######################
    # Probe Z Minus direction and set Z0 in current WCO
    # End at Z_clearance above workpiece
    def probe_down(self):
        method = 'probe_down'
        self.commands.append(f"G91 G38.2 Z-{self.parms['max_z']} F{self.parms['search_vel']}")
        self.commands.append(f"G1 Z{self.parms['retract']} F{self.parms['rapid_vel']}")
        self.commands.append("G4 P0.5")
        self.commands.append(f"G38.2 Z-{1.2 * self.parms['retract']} F{self.parms['probe_vel']}")
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} failed: {rtn}'
        self.set_zero("Z")
        self.commands.append(f"G1 Z{self.parms['z_clearance']} F{self.parms['rapid_vel']}")
        self.commands.append('G90')
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} failed: {rtn}'
        a = STATUS.get_probed_position_with_offsets()
        self.status['z'] = float(a[2])
        self.add_history(method, 'z')
        return 1

##################
# Boss, Pocket, Ridge, Valley
##################
    def probe_round_boss(self):
        if self.parms['diameter_hint'] <= 0:
            return 'Boss diameter hint must be larger than 0'
        pos = self.get_current_position()
        radius = self.parms['diameter_hint'] / 2
        x1 = pos[0] - radius - self.parms['stepoff']
        x2 = pos[0] + radius + self.parms['stepoff']
        y1 = pos[1] - radius - self.parms['stepoff']
        y2 = pos[1] + radius + self.parms['stepoff']
        error = self.probe_outside_length_x(x1, x2)
        if error != 1: return error
        error = self.probe_outside_length_y(y1, y2)
        if error != 1: return error
        self.status['d'] = (self.status['lx'] + self.status['ly']) / 2
        return 1

    def probe_round_pocket(self):
        if self.parms['diameter_hint'] <= 0:
            return 'Pocket diameter hint must be larger than 0'
        if self.parms['probe_diam'] >= self.parms['diameter_hint']:
            return 'Probe diameter too large for hole diameter hint'
        pos = self.get_current_position()
        radius = self.parms['diameter_hint'] / 2
        x1 = pos[0] - radius + self.parms['stepoff']
        x2 = pos[0] + radius - self.parms['stepoff']
        y1 = pos[1] - radius + self.parms['stepoff']
        y2 = pos[1] + radius - self.parms['stepoff']
        error = self.probe_inside_length_x(x1, x2)
        if error != 1: return error
        error = self.probe_inside_length_y(y1, y2)
        if error != 1: return error
        self.status['d'] = (self.status['lx'] + self.status['ly']) / 2
        return 1

    def probe_rectangular_boss(self):
        if self.parms['y_hint'] <= 0:
            return 'Y length hint must be larger than 0'
        if self.parms['x_hint'] <= 0:
            return 'X length hint must be larger than 0'
        pos = self.get_current_position()
        x1 = pos[0] - (self.parms['x_hint'] / 2) - self.parms['stepoff']
        x2 = pos[0] + (self.parms['x_hint'] / 2) + self.parms['stepoff']
        y1 = pos[1] - (self.parms['y_hint'] / 2) - self.parms['stepoff']
        y2 = pos[1] + (self.parms['y_hint'] / 2) + self.parms['stepoff']
        error = self.probe_outside_length_x(x1, x2)
        if error != 1: return error
        error = self.probe_outside_length_y(y1, y2)
        if error != 1: return error
        return 1

    def probe_rectangular_pocket(self):
        if self.parms['y_hint'] <= 0:
            return 'Y length hint must be larger than 0'
        if self.parms['x_hint'] <= 0:
            return 'X length hint must be larger than 0'
        if self.parms['probe_diam'] >= self.parms['y_hint'] / 2:
            return 'Probe diameter too large for Y length hint'
        if self.parms['probe_diam'] >= self.parms['x_hint'] / 2:
            return 'Probe diameter too large for X length hint'
        pos = self.get_current_position()
        x1 = pos[0] - (self.parms['x_hint'] / 2) + self.parms['stepoff']
        x2 = pos[0] + (self.parms['x_hint'] / 2) - self.parms['stepoff']
        y1 = pos[1] - (self.parms['y_hint'] / 2) + self.parms['stepoff']
        y2 = pos[1] + (self.parms['y_hint'] / 2) - self.parms['stepoff']
        error = self.probe_inside_length_x(x1, x2)
        if error != 1: return error
        error = self.probe_inside_length_y(y1, y2)
        return error

    def probe_ridge_x(self):
        if self.parms['x_hint'] <= 0:
            return 'X length hint must be larger than 0'
        pos = self.get_current_position()
        x1 = pos[0] - (self.parms['x_hint'] / 2) - self.parms['stepoff']
        x2 = pos[0] + (self.parms['x_hint'] / 2) + self.parms['stepoff']
        error = self.probe_outside_length_x(x1, x2)
        return error

    def probe_ridge_y(self):
        if self.parms['y_hint'] <= 0:
            return 'Y length hint must be larger than 0'
        pos = self.get_current_position()
        y1 = pos[1] - (self.parms['y_hint'] / 2) - self.parms['stepoff']
        y2 = pos[1] + (self.parms['y_hint'] / 2) + self.parms['stepoff']
        error = self.probe_outside_length_y(y1, y2)
        return error

    def probe_valley_x(self):
        if self.parms['x_hint'] <= 0:
            return 'X length hint must be larger than 0'
        if self.parms['probe_diam'] >= self.parms['x_hint'] / 2:
            return 'Probe diameter too large for X length hint'
        pos = self.get_current_position()
        x1 = pos[0] - (self.parms['x_hint'] / 2) + self.parms['stepoff']
        x2 = pos[0] + (self.parms['x_hint'] / 2) - self.parms['stepoff']
        error = self.probe_inside_length_x(x1, x2)
        return error

    def probe_valley_y(self):
        if self.parms['y_hint'] <= 0:
            return 'Y length hint must be larger than 0'
        if self.parms['probe_diam'] >= self.parms['y_hint'] / 2:
            return 'Probe diameter too large for Y length hint'
        pos = self.get_current_position()
        y1 = pos[1] - (self.parms['y_hint'] / 2) + self.parms['stepoff']
        y2 = pos[1] + (self.parms['y_hint'] / 2) - self.parms['stepoff']
        error = self.probe_inside_length_y(y1, y2)
        return error

    def probe_outside_length_x(self, x1, x2):
        method = 'probe_outside_length_x:'
        self.commands.append(f"G90 G1 X{x1:{self.tpl}} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'xp'))
        self.commands.append(self.z_clearance_up)
        self.commands.append(f"G90 G1 X{x2:{self.tpl}} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'xm'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        self.status['xc'] = (self.status['xp'] + self.status['xm']) / 2
        self.status['lx'] = abs(self.status['xp'] - self.status['xm'])
        # move X to new center
        rtn = self.CALL_MDI_WAIT(f"G90 G1 X{self.status['xc']:{self.tpl}} F{self.parms['rapid_vel']}") 
        if rtn != 1:
            return f'{method} {rtn}'
        self.add_history(method, 'xm', 'xc', 'xp', 'lx')
        self.set_zero("X")
        return 1

    def probe_outside_length_y(self, y1, y2):
        method = 'probe_outside_length_y:'
        self.commands.append(f"G90 G1 Y{y1:{self.tpl}} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'yp'))
        self.commands.append(self.z_clearance_up)
        self.commands.append(f"G90 G1 Y{y2:{self.tpl}} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'ym'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        self.status['yc'] = (self.status['yp'] + self.status['ym']) / 2
        self.status['ly'] = abs(self.status['yp'] - self.status['ym'])
        # move Y to new center
        rtn = self.CALL_MDI_WAIT(f"G90 G1 Y{self.status['yc']:{self.tpl}} F{self.parms['rapid_vel']}") 
        if rtn != 1:
            return f'{method} {rtn}'
        self.add_history(method, 'ym', 'yc', 'yp', 'ly')
        self.set_zero("Y")
        return 1

    def probe_inside_length_x(self, x1, x2):
        method = 'probe_inside_length_x:'
        self.commands.append(f"G90 G1 X{x1:{self.tpl}} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'xm'))
        self.commands.append(self.z_clearance_up)
        self.commands.append(f"G90 G1 X{x2:{self.tpl}} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'xp'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList() 
        if rtn != 1:
            return f'{method} {rtn}'
        self.status['xc'] = (self.status['xm'] + self.status['xp']) / 2
        self.status['lx'] = abs(self.status['xp'] - self.status['xm'])
        # move X to new center
        rtn = self.CALL_MDI_WAIT(f"G90 G1 X{self.status['xc']:{self.tpl}} F{self.parms['rapid_vel']}") 
        if rtn != 1:
            return f'{method} {rtn}'
        self.add_history(method, 'xm', 'xc', 'xp', 'lx')
        self.set_zero("X")
        return 1

    def probe_inside_length_y(self, y1, y2):
        method = 'probe_inside_length_y:'
        self.commands.append(f"G90 G1 Y{y1:{self.tpl}} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'ym'))
        self.commands.append(self.z_clearance_up)
        self.commands.append(f"G90 G1 Y{y2:{self.tpl}} F{self.parms['rapid_vel']}")
        self.commands.append(self.z_clearance_down)
        self.commands.append((self.probe, 'yp'))
        self.commands.append(self.z_clearance_up)
        rtn = self.cmdList()
        if rtn != 1:
            return f'{method} {rtn}'
        self.status['yc'] = (self.status['ym'] + self.status['yp']) / 2
        self.status['ly'] = abs(self.status['yp'] - self.status['ym'])
        # move Y to new center
        rtn = self.CALL_MDI_WAIT(f"G90 G1 Y{self.status['yc']:{self.tpl}} F{self.parms['rapid_vel']}") 
        if rtn != 1:
            return f'{method} {rtn}'
        self.add_history(method, 'ym', 'yc', 'yp', 'ly')
        self.set_zero("Y")
        return 1

#############
# Calibration
#############
    def probe_cal_round_pocket(self):
        # reset calibration offset to 0
        self.probe_radius = self.parms['probe_diam'] / 2
        error = self.probe_round_pocket()
        if error != 1: return error
        # repeat but this time start from calculated center
        error = self.probe_round_pocket()
        if error != 1: return error
        # calculate calibration offset
        self.status['offset'] = self.get_new_offset('r')
        return 1

    def probe_cal_square_pocket(self):
        # reset calibration offset to 0
        self.probe_radius = self.parms['probe_diam'] / 2
        error = self.probe_rectangular_pocket()
        if error != 1: return error
        # repeat but this time start from calculated center
        error = self.probe_rectangular_pocket()
        if error != 1: return error
        self.status['offset'] = self.get_new_offset('s')
        return 1

    def probe_cal_round_boss(self):
        # reset calibration offset to 0
        self.probe_radius = self.parms['probe_diam'] / 2
        error = self.probe_round_boss()
        if error != 1: return error
        # repeat but this time start from calculated center
        error = self.probe_round_boss()
        if error != 1: return error
        self.status['offset'] = self.get_new_offset('r')
        return 1

    def probe_cal_square_boss(self):
        # reset calibration offset to 0
        self.probe_radius = self.parms['probe_diam'] / 2
        error = self.probe_rectangular_boss()
        if error != 1: return error
        # repeat but this time start from calculated center
        error = self.probe_rectangular_boss()
        if error != 1: return error
        self.status['offset'] = self.get_new_offset('s')
        return 1

    def get_new_offset(self, shape):
        if shape == 'r':
            base_x = base_y = self.parms['diameter_hint']
        elif shape == 's':
            base_x = self.parms['x_hint']
            base_y = self.parms['y_hint']
        else: return 0
        xcal_error = self.status['lx'] - base_x
        ycal_error = self.status['ly'] - base_y
        new_cal_avg = (xcal_error + ycal_error) / 2
        if self.cal_x_error is True: return xcal_error
        elif self.cal_y_error is True: return ycal_error
        else: return new_cal_avg

