#!/usr/bin/env python3
# QtDragon - tool probing routines
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

import sys
from qtvcp.core import Status, Info

STATUS = Status()
INFO = Info()

class ToolRoutines():
    def __init__(self):
        pass

    def tool_ts_z(self):
        method = 'probe_ts_z:'
        pos = self.get_current_position()[2]
        try:
            # basic sanity checks
            if self.ts_data['ts_max'] is None:
                return 'Missing toolsetter setting: ts_max'

            self.commands.append('G49')
            self.commands.append('G91')
            self.commands.append(f"G38.2 Z-{self.parms['max_z']} F{self.parms['search_vel']}")
            self.commands.append(f"G1 Z{self.parms['retract']} F{self.parms['rapid_vel']}")
            self.commands.append(f"F{self.parms['probe_vel']}")
            self.commands.append(f"G38.2 Z-{self.parms['retract'] * 1.2}")
            self.commands.append(f"G90 G1 Z{pos:.3f} F{self.parms['rapid_vel']}")
            rtn = self.cmdList()
            if rtn != 1:
                return f'{method} {rtn}'
            h = STATUS.get_probed_position()[2]
            self.ts_status['th'] = abs(float(h))
            # report success
            return 1
        except Exception as e:
            return f'{e}'

