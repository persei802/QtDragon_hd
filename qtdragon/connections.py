#!/usr/bin/python3

class Connections():
    def __init__(self, parent, widget):
        self.w = widget
        self.parent = parent
        # DRO buttons
        self.w.btn_show_macros.clicked.connect(self.parent.show_macros_clicked)
        self.w.systemtoolbutton.toggled.connect(lambda state: self.parent.systemtoolbutton_toggled(state))
        # jog buttons
        self.w.jog_xy.joy_btn_pressed.connect(self.parent.jog_xy_pressed)
        self.w.jog_xy.joy_btn_released.connect(self.parent.jog_xy_released)
        self.w.jog_az.joy_btn_pressed.connect(self.parent.jog_az_pressed)
        self.w.jog_az.joy_btn_released.connect(self.parent.jog_az_released)
        # program control buttons
        self.w.btn_stop.pressed.connect(self.parent.btn_stop_pressed)
        self.w.btn_cycle_start.pressed.connect(self.parent.btn_run_pressed)
        self.w.btn_reload.pressed.connect(self.parent.btn_reload_pressed)
        self.w.btn_pause.pressed.connect(self.parent.btn_pause_pressed)
        self.w.btn_pause_spindle.clicked.connect(self.parent.btn_pause_spindle_clicked)
        self.w.btn_enable_comp.clicked.connect(self.parent.btn_enable_comp_clicked)
        # menu buttons
        self.w.btn_save_log.pressed.connect(self.parent.btn_save_log_pressed)
        self.w.btn_clear_status.clicked.connect(self.parent.btn_clear_status_clicked)
        self.w.btn_home_all.clicked.connect(self.parent.btn_home_all_clicked)
        self.w.btn_ref_laser.clicked.connect(self.parent.btn_ref_laser_clicked)
        self.w.btn_ref_camera.clicked.connect(self.parent.btn_ref_camera_clicked)
        self.w.btn_goto_zero.clicked.connect(self.parent.btn_goto_location_clicked)
        self.w.btn_rewind_a.clicked.connect(self.parent.btn_rewind_clicked)
        self.w.btn_go_home.clicked.connect(self.parent.btn_goto_location_clicked)
        # tool frame buttons
        self.w.btn_goto_sensor.clicked.connect(self.parent.btn_goto_location_clicked)
        self.w.btn_touchoff.pressed.connect(self.parent.btn_touchoff_pressed)
        # file page buttons
        self.w.btn_copy_right.pressed.connect(self.parent.copy_file)
        self.w.btn_copy_left.pressed.connect(self.parent.copy_file)
        self.w.btn_delete.pressed.connect(self.parent.delete_file)
        self.w.btn_rename.pressed.connect(self.parent.rename_file)
        self.w.btn_load_file.pressed.connect(self.parent.load_file)
        self.w.btn_new_folder.pressed.connect(self.parent.new_folder)
        self.w.btn_edit_gcode.pressed.connect(self.parent.edit_gcode)
        self.w.btn_clear_program_history.pressed.connect(lambda: self.w.cmb_program_history.clear())
        # tool page buttons
        self.w.btn_add_tool.pressed.connect(self.parent.btn_add_tool_pressed)
        self.w.btn_delete_tool.pressed.connect(self.parent.btn_delete_tool_pressed)
        self.w.btn_load_tool.pressed.connect(self.parent.btn_load_tool_pressed)
        self.w.btn_unload_tool.pressed.connect(self.parent.btn_unload_tool_pressed)
        self.w.btn_db_help.pressed.connect(self.parent.show_db_help_page)
        # gcode viewer
        self.w.btn_edit_gcode.clicked.connect(lambda state: self.parent.edit_gcode_changed(state))
        # graphic display buttons
        self.w.btn_alpha_mode.clicked.connect(lambda state: self.w.gcodegraphics.set_alpha_mode(state))
        self.w.btn_dimensions.clicked.connect(lambda state: self.parent.btn_dimensions_changed(state))
        # checkboxes
        self.w.chk_run_from_line.stateChanged.connect(lambda state: self.parent.chk_run_from_line_changed(state))
        self.w.chk_inhibit_selection.stateChanged.connect(lambda state: self.w.gcodegraphics.set_inhibit_selection(state))
        self.w.chk_use_mpg.stateChanged.connect(lambda state: self.parent.use_mpg_changed(state))
        self.w.chk_override_limits.stateChanged.connect(lambda state: self.parent.override_limits_changed(state))
        self.w.chk_use_camera.stateChanged.connect(lambda state: self.parent.use_camera_changed(state))
        self.w.chk_use_mdi_keyboard.stateChanged.connect(lambda state: self.w.mdi_keyboard.setVisible(state))
        self.w.chk_use_basic_calculator.stateChanged.connect(lambda state: self.parent.chk_use_basic_calc(state))
        self.w.chk_use_handler_calculator.stateChanged.connect(lambda state: self.parent.event_filter.set_dialog_mode(state))
        self.w.chk_touchplate.stateChanged.connect(lambda state: self.parent.touchoff_changed(state))
        self.w.chk_manual_toolsensor.stateChanged.connect(lambda state: self.parent.touchoff_changed(state))
        self.w.chk_auto_toolsensor.stateChanged.connect(lambda state: self.parent.touchoff_changed(state))
        # sliders
        self.w.cam_diameter.valueChanged.connect(lambda value: self.parent.cam_dia_changed(value))
        self.w.cam_rotate.valueChanged.connect(lambda value: self.parent.cam_rot_changed(value))
        # comboboxes
        self.w.cmb_program_history.activated.connect(self.parent.cmb_program_history_activated)
        # spinboxes
        self.w.spinBox_duration.valueChanged.connect(self.parent.status_duration_changed)
        # lineEdits
        self.w.lineEdit_max_power.editingFinished.connect(self.parent.max_power_edited)
        self.w.lineEdit_max_volts.editingFinished.connect(self.parent.max_volts_edited)
        self.w.lineEdit_max_amps.editingFinished.connect(self.parent.max_amps_edited)
        # misc
        self.w.gcode_viewer.percentDone.connect(lambda percent: self.parent.percent_done_changed(percent))
        self.w.gcodegraphics.percentLoaded.connect(lambda percent: self.parent.percent_loaded_changed(percent))
