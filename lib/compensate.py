#!/usr/bin/env python3
#Copyright (C) 2026 Jim Sloot(persei802@gmail.com
#This program is free software; you can redistribute it and/or modify
#it under the terms of the GNU 2 General Public License as published by
#the Free Software Foundation; either version 2 of the License, or
#(at your option) any later version.

#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with this program; if not, write to the Free Software
#Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import sys
import os
import mmap
import hal
import time
import linuxcnc
import struct
import numpy as np

from enum import Enum, unique

SHM_PATH = '/dev/shm/linuxcnc_surface_map'
MAX_NX = 200
MAX_NY = 200
HEADER_SIZE = 44

@unique
class State(Enum):
    START = 1
    IDLE = 2
    RUNNING = 3
    RESET = 4
    STOP = 5


class SurfaceMap:
    def __init__(self):
        self.shm = None
        self.attached = False
        self.version = -1
        self.grid = None

    def attach_shm(self):
        try:
            fd = os.open(SHM_PATH, os.O_RDWR)
            shm = mmap.mmap(fd, 0, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
            os.close(fd)
        except FileNotFoundError:
            return None
        return shm

    def check_update(self, shm):
        version = struct.unpack_from("I", shm, 0)[0]
        if version == self.version or version % 2:
            return False
        self.version = version
        nx = struct.unpack_from("I", shm, 4)[0]
        ny = struct.unpack_from("I", shm, 8)[0]
        xmin = struct.unpack_from("d", shm, 12)[0]
        xmax = struct.unpack_from("d", shm, 20)[0]
        ymin = struct.unpack_from("d", shm, 28)[0]
        ymax = struct.unpack_from("d", shm, 36)[0]
        offset = HEADER_SIZE
        size = nx * ny * 8
        z = np.frombuffer(shm[offset:offset+size], dtype=np.float64).copy()
        z = z.reshape((nx, ny))

        self.grid = {
            "nx": nx,
            "ny": ny,
            "xmin": xmin,
            "xmax": xmax,
            "ymin": ymin,
            "ymax": ymax,
            "z": z}        
        return True

    def interpolate(self, x, y):
        nx = self.grid["nx"]
        ny = self.grid["ny"]
        xmin = self.grid["xmin"]
        xmax = self.grid["xmax"]
        ymin = self.grid["ymin"]
        ymax = self.grid["ymax"]
        z = self.grid["z"]

        fx = (x - xmin) / (xmax - xmin) * (nx - 1)
        fy = (y - ymin) / (ymax - ymin) * (ny - 1)

        xi = int(fx)
        yi = int(fy)
        
        if xi < 0 or yi < 0 or xi >= nx-1 or yi >= ny-1: return 0

        dx = fx - xi
        dy = fy - yi

        z00 = z[xi,yi]
        z10 = z[xi+1,yi]
        z01 = z[xi,yi+1]
        z11 = z[xi+1,yi+1]

        return (
            z00*(1-dx)*(1-dy) +
            z10*dx*(1-dy) +
            z01*(1-dx)*dy +
            z11*dx*dy)

class HALComp:
    def __init__(self):
        self.h = hal.component("compensate")
        self.h.newpin("enable", hal.HAL_BIT, hal.HAL_IN)
        self.h.newpin("clear", hal.HAL_BIT, hal.HAL_OUT)
        self.h.newpin("scale", hal.HAL_S32, hal.HAL_IN)
        self.h.newpin("z-offset", hal.HAL_S32, hal.HAL_OUT)
        self.h.ready()
        self.map = SurfaceMap()
        self.stat = linuxcnc.stat()
        self.shm = None

    def run(self):
        currentState = State.START
        self.h["z-offset"] = 0
        try:
            while True:
                if currentState == State.START:
                    self.shm = self.map.attach_shm()
                    if self.shm is not None:
                        currentState = State.IDLE

                elif currentState == State.IDLE:
                    if self.h['enable']:
                        currentState = State.RUNNING
                        
                elif currentState == State.RUNNING:
                    self.map.check_update(self.shm)
                    self.stat.poll()
                    if self.h['enable']:
                        if self.stat.task_state == linuxcnc.STATE_ON:
                            x = self.stat.position[0] - self.stat.g5x_offset[0] - self.stat.g92_offset[0]
                            y = self.stat.position[1] - self.stat.g5x_offset[1] - self.stat.g92_offset[1]
                            offset = self.map.interpolate(x, y)
                            self.h["z-offset"] = int(offset * self.h["scale"])
                        else:
                            self.h["z-offset"] = 0
                    else:
                        currentState = State.RESET

                elif currentState == State.RESET:
                    self.h["z-offset"] = 0
                    # toggle the clear output
                    self.h["clear"] = 1;
                    time.sleep(0.1)
                    self.h["clear"] = 0;
                    currentState = State.IDLE
                time.sleep(0.02)
        except KeyboardInterrupt:
            raise SystemExit

comp = HALComp()
comp.run()
