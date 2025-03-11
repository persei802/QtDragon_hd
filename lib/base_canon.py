#!/usr/bin/env python
import math
import gcode
import linuxcnc


class BaseCanon(object):
    def __init__(self):
        self.feedrate = 1
        self.dwell_time = 0
        self.tool_list = []
        self.preview_zero_rxy = []
        self.seq_num = -1
        self.lo = (0,) * 9
        self.first_move = True
        self.in_arc = 0
        self.xo = self.yo = self.zo = self.ao = self.bo = self.co = self.uo = self.vo = self.wo = 0
        self.suppress = 0

        self.plane = 1
        self.arcdivision = 64
        self.arcfeed = []
        self.feed = []
        self.traverse = []

        # extents
        self.min_extents = [9e99, 9e99, 9e99]
        self.max_extents = [-9e99, -9e99, -9e99]
        self.min_extents_notool = [9e99, 9e99, 9e99]
        self.max_extents_notool = [-9e99, -9e99, -9e99]
        self.min_extents_zero_rxy = [9e99,9e99,9e99]
        self.max_extents_zero_rxy = [-9e99,-9e99,-9e99]
        self.min_extents_notool_zero_rxy = [9e99,9e99,9e99]
        self.max_extents_notool_zero_rxy = [-9e99,-9e99,-9e99]

        # tool length offsets
        self.tlo_x = 0.0
        self.tlo_y = 0.0
        self.tlo_z = 0.0
        self.tlo_a = 0.0
        self.tlo_b = 0.0
        self.tlo_c = 0.0
        self.tlo_u = 0.0
        self.tlo_v = 0.0
        self.tlo_w = 0.0

        self.tool_offsets = (0.0,) * 9

        # G92/G52 offsets
        self.g92_offset_x = 0.0
        self.g92_offset_y = 0.0
        self.g92_offset_z = 0.0
        self.g92_offset_a = 0.0
        self.g92_offset_b = 0.0
        self.g92_offset_c = 0.0
        self.g92_offset_u = 0.0
        self.g92_offset_v = 0.0
        self.g92_offset_w = 0.0
        self.origin = 540

        # g5x offsets
        self.g5x_offset_x = 0.0
        self.g5x_offset_y = 0.0
        self.g5x_offset_z = 0.0
        self.g5x_offset_a = 0.0
        self.g5x_offset_b = 0.0
        self.g5x_offset_c = 0.0
        self.g5x_offset_u = 0.0
        self.g5x_offset_v = 0.0
        self.g5x_offset_w = 0.0

        # XY rotation (degrees)
        self.rotation_xy = 0
        self.rotation_cos = 1
        self.rotation_sin = 0

    def comment(self, msg):
        pass

    def message(self, msg):
        pass

    def check_abort(self):
        pass

    def next_line(self, st):
        # state attributes
        # 'block', 'cutter_side', 'distance_mode', 'feed_mode', 'feed_rate',
        # 'flood', 'gcodes', 'mcodes', 'mist', 'motion_mode', 'origin', 'units',
        # 'overrides', 'path_mode', 'plane', 'retract_mode', 'sequence_number',
        # 'speed', 'spindle', 'stopping', 'tool_length_offset', 'toolchange',
        self.state = st
        self.seq_num = self.state.sequence_number

    def calc_extents(self):
        if not self.arcfeed and not self.feed and not self.traverse:
            self.min_extents = \
            self.max_extents = \
            self.min_extents_notool = \
            self.max_extents_notool = \
            self.min_extents_zero_rxy = \
            self.max_extents_zero_rxy = \
            self.min_extents_notool_zero_rxy = \
            self.max_extents_notool_zero_rxy = [0,0,0]
            return
        self.min_extents, self.max_extents, self.min_extents_notool, \
        self.max_extents_notool = gcode.calc_extents(self.arcfeed, self.feed, self.traverse)
        self.unrotate_preview()
        self.min_extents_zero_rxy, self.max_extents_zero_rxy, self.min_extents_notool_zero_rxy, self.max_extents_notool_zero_rxy = gcode.calc_extents(self.preview_zero_rxy)

    def rotate_and_translate(self, x, y, z, a, b, c, u, v, w):
        x += self.g92_offset_x
        y += self.g92_offset_y
        z += self.g92_offset_z
        a += self.g92_offset_a
        b += self.g92_offset_b
        c += self.g92_offset_c
        u += self.g92_offset_u
        v += self.g92_offset_v
        w += self.g92_offset_w

        if self.rotation_xy:
            rotx = x * self.rotation_cos - y * self.rotation_sin
            roty = x * self.rotation_sin + y * self.rotation_cos
            x, y = rotx, roty

        x += self.g5x_offset_x
        y += self.g5x_offset_y
        z += self.g5x_offset_z
        a += self.g5x_offset_a
        b += self.g5x_offset_b
        c += self.g5x_offset_c
        u += self.g5x_offset_u
        v += self.g5x_offset_v
        w += self.g5x_offset_w

        return [x, y, z, a, b, c, u, v, w]

    def set_g5x_offset(self, index, x, y, z, a, b, c, u, v, w):
        self.origin = index
        self.g5x_offset_x = x
        self.g5x_offset_y = y
        self.g5x_offset_z = z
        self.g5x_offset_a = a
        self.g5x_offset_b = b
        self.g5x_offset_c = c
        self.g5x_offset_u = u
        self.g5x_offset_v = v
        self.g5x_offset_w = w

    def set_g92_offset(self, x, y, z, a, b, c, u, v, w):
        self.g92_offset_x = x
        self.g92_offset_y = y
        self.g92_offset_z = z
        self.g92_offset_a = a
        self.g92_offset_b = b
        self.g92_offset_c = c
        self.g92_offset_u = u
        self.g92_offset_v = v
        self.g92_offset_w = w

    def set_xy_rotation(self, rotation):
        self.rotation_xy = rotation
        theta = math.radians(rotation)
        self.rotation_cos = math.cos(theta)
        self.rotation_sin = math.sin(theta)

    def tool_offset(self, xo, yo, zo, ao, bo, co, uo, vo, wo):
        self.first_move = True
        x, y, z, a, b, c, u, v, w = self.lo

        self.lo = (
            x - xo + self.tlo_x, y - yo + self.tlo_y, z - zo + self.tlo_z,
            a - ao + self.tlo_a, b - bo + self.tlo_b, c - bo + self.tlo_b,
            u - uo + self.tlo_u, v - vo + self.tlo_v, w - wo + self.tlo_w)

        self.tlo_x = xo
        self.tlo_y = yo
        self.tlo_z = zo
        self.tlo_a = ao
        self.tlo_b = bo
        self.tlo_c = co
        self.tlo_u = uo
        self.tlo_v = vo
        self.tlo_w = wo

        self.tool_offsets = xo, yo, zo, ao, bo, co, uo, vo, wo

    def unrotate_preview(self):
        angle = math.radians(-self.rotation_xy)
        cos = math.cos(angle)
        sin = math.sin(angle)
        g5x_x = self.g5x_offset_x
        g5x_y = self.g5x_offset_y
        for movelist in self.feed, self.arcfeed:
            for linenum, start, end, feed, tooloffset in movelist:
                tsx = start[0] - g5x_x
                tsy = start[1] - g5x_y
                tex = end[0] - g5x_x
                tey = end[1] - g5x_y
                rsx = (tsx * cos) - (tsy * sin) + g5x_x
                rsy = (tsx * sin) + (tsy * cos) + g5x_y
                rex = (tex * cos) - (tey * sin) + g5x_x
                rey = (tex * sin) + (tey * cos) + g5x_y
                self.preview_zero_rxy.append((linenum, (rsx, rsy) + start[2:], (rex, rey) + end[2:], feed, tooloffset))
        for linenum, start, end, tooloffset in self.traverse:
            tsx = start[0] - g5x_x
            tsy = start[1] - g5x_y
            tex = end[0] - g5x_x
            tey = end[1] - g5x_y
            rsx = (tsx * cos) - (tsy * sin) + g5x_x
            rsy = (tsx * sin) + (tsy * cos) + g5x_y
            rex = (tex * cos) - (tey * sin) + g5x_x
            rey = (tex * sin) + (tey * cos) + g5x_y
            self.preview_zero_rxy.append((linenum, (rsx, rsy) + start[2:], (rex, rey) + end[2:], tooloffset))

    def set_spindle_rate(self, speed):
        pass

    def set_feed_rate(self, feed_rate):
        self.feedrate = feed_rate / 60.

    def select_plane(self, plane):
        pass

    def change_tool(self, pocket):
        self.first_move = True
        try:
            self.tool_list.append(pocket)
        except Exception as e:
            print(e)

    def get_tool(self, pocket):
        return -1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0

    def straight_traverse(self, x, y, z, a, b, c, u, v, w):
        if self.suppress > 0: return
        pos = self.rotate_and_translate(x, y, z, a, b, c, u, v, w)
        if not self.first_move:
            self.traverse.append((self.seq_num, self.lo, pos, (self.xo, self.yo, self.zo)))
            self.add_path_point('traverse', self.lo, pos)
        self.lo = pos

    def rigid_tap(self, x, y, z):
        if self.suppress > 0:
            return

        self.first_move = False
        pos = self.rotate_and_translate(x, y, z, 0, 0, 0, 0, 0, 0)[:3]
        pos += self.lo[3:]
        self.add_path_point('feed', self.lo, pos)

    def set_plane(self, plane):
        self.plane = plane

    def arc_feed(self, *args):
        if self.suppress > 0: return
        self.first_move = False
        self.in_arc = True
        try:
            segs = gcode.arc_to_segments(self, *args, self.arcdivision)
            self.straight_arcsegments(segs)
        finally:
            self.in_arc = False

    def straight_arcsegments(self, segs):
        self.first_move = False
        last_pos = self.lo
        feedrate = self.feedrate
        to = (self.xo, self.yo, self.zo)
        for pos in segs:
            self.arcfeed.append((self.seq_num, last_pos, pos, feedrate, to))
            self.add_path_point('arcfeed', last_pos, pos)
            last_pos = pos
        self.lo = last_pos

    def straight_feed(self, x, y, z, a, b, c, u, v, w):
        if self.suppress > 0: return
        self.first_move = False
        pos = self.rotate_and_translate(x, y, z, a, b, c, u, v, w)
        self.feed.append((self.seq_num, self.lo, pos, self.feedrate, (self.xo, self.yo, self.zo)))
        self.add_path_point('feed', self.lo, pos)
        self.lo = pos

    straight_probe = straight_feed

    def user_defined_function(self, i, p, q):
        if self.suppress > 0:
            return

        self.add_path_point('user', self.lo, self.lo)

    def dwell(self, arg):
        if self.suppress > 0: return
        self.dwell_time += arg
        color = self.colors['dwell']
        self.dwells.append((self.seq_num, color, self.lo[0], self.lo[1], self.lo[2], int(self.state.plane/10-17)))
        self.add_path_point('dwell', self.lo, self.lo)

    def get_external_angular_units(self):
        return 1.0

    def get_external_length_units(self):
        return 1.0

    def get_axis_mask(self):
        return 0

    def get_block_delete(self):
        return 0


class StatCanon(BaseCanon):
    def __init__(self, geometry='XYZ', random=False, stat=None):
        super(StatCanon, self).__init__()
        self.geometry = geometry
        self.random = random
        self.stat = stat or linuxcnc.stat()
        self.stat.poll()
        self.tools = list(self.stat.tool_table)

    def get_tool(self, pocket):
        if pocket >= 0 and pocket < len(self.tools):
            return tuple(self.tools[pocket])
        return -1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0

    def get_external_angular_units(self):
        return self.stat.angular_units or 1.0

    def get_external_length_units(self):
        return self.stat.linear_units or 1.0

    def get_axis_mask(self):
        return self.stat.axis_mask

    def get_block_delete(self):
        return self.stat.block_delete

class PrintCanon(BaseCanon):
    def set_g5x_offset(self, *args):
        print("set_g5x_offset", args)

    def set_g92_offset(self, *args):
        print("set_g92_offset", args)

    def next_line(self, state):
        print("next_line", state.sequence_number)
        self.state = state

    def set_plane(self, plane):
        print("set plane", plane)

    def set_feed_rate(self, arg):
        print("set feed rate", arg)

    def comment(self, arg):
        print("#", arg)

    def straight_traverse(self, *args):
        print("straight_traverse %.4g %.4g %.4g  %.4g %.4g %.4g   %.4g %.4g %.4g" % args)

    def straight_feed(self, *args):
        print("straight_feed %.4g %.4g %.4g  %.4g %.4g %.4g  %.4g %.4g %.4g" % args)

    def dwell(self, arg):
        if arg < .1:
            print("dwell %f ms" % (1000 * arg))
        else:
            print("dwell %f seconds" % arg)

    def arc_feed(self, *args):
        print("arc_feed %.4g %.4g  %.4g %.4g %.4g  %.4g  %.4g %.4g %.4g" % args)

    def get_axis_mask(self):
        return 7  # XYZ
