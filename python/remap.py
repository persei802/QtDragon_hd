from interpreter import *
import emccanon

def m6_remap(self, **words):
    if not self.task:
        yield INTERP_OK
        return

    current_tool = self.current_tool
    selected_tool = self.selected_tool
    current_pocket = self.current_pocket
    selected_pocket = self.selected_pocket

    self.execute("G49")
    try:
        self.selected_pocket =  int(selected_pocket)
        emccanon.CHANGE_TOOL()
        self.current_pocket = self.selected_pocket
        self.selected_pocket = -1
        self.selected_tool = -1
        # cause a sync()
        self.set_tool_parameters()
        self.toolchange_flag = True
    except InterpreterException as e:
        self.set_errormsg(f"M6 remap error: {e}")
        yield INTERP_ERROR
        return
    yield INTERP_EXECUTE_FINISH
    # M6 is now complete
    # check if auto tool touchoff is enabled
    auto_touchoff = int(self.params['_auto_touchoff'])
    if auto_touchoff == 0:
        yield INTERP_OK
        return
    # these are WCS coordinates
    x0 = emccanon.GET_EXTERNAL_POSITION_X()
    y0 = emccanon.GET_EXTERNAL_POSITION_Y()
    z0 = emccanon.GET_EXTERNAL_POSITION_Z()
    work_height = float(self.params['_work_height'])
    sensor_height = float(self.params['_sensor_height'])
    sensor_x = float(self.params['_sensor_x'])
    sensor_y = float(self.params['_sensor_y'])
    search_vel = float(self.params['_search_vel'])
    probe_vel = float(self.params['_probe_vel'])
    max_probe = float(self.params['_max_probe'])
    retract = float(self.params['_retract'])
    zsafe = float(self.params['_zsafe'])
    try:
        # move to tool sensor position
        self.execute("G90")
        self.execute("G53 G0 Z0")
        self.execute(f"G53 G0 X{sensor_x} Y{sensor_y}")
        # incremental mode
        self.execute("G91")
        # fast probe down
        self.execute(f"G38.2 Z-{max_probe} F{search_vel}")
        yield INTERP_EXECUTE_FINISH
        if self.params[5070] == 0 or self.return_value > 0.0:
            self.execute("G90")
            self.set_errormsg("tool_probe_m6 remap error:")
            yield INTERP_ERROR
            return
        # retract
        self.execute(f"G1 Z{retract}")
        # slow probe down
        self.execute(f"G38.2 Z-{retract * 1.2} F{probe_vel}")
        yield INTERP_EXECUTE_FINISH
        if self.params[5070] == 0 or self.return_value > 0.0:
            self.execute("G90")
            self.set_errormsg("tool_probe_m6 remap error:")
            yield INTERP_ERROR
            return
        self.execute("G90")
        # calculate Z0 height
        self.execute(f"G10 L20 P0 Z{sensor_height - work_height}")
        # return to original position
        self.execute(f"G0 Z{z0:.3f}")
        yield INTERP_EXECUTE_FINISH
        self.execute(f"G0 X{x0:.3f} Y{y0:.3f}")
    except InterpreterException as e:
        msg = f"{e.line_number}: {e.line_text} - {e.error_message}"
        print(msg)
        yield INTERP_ERROR

    yield INTERP_OK
