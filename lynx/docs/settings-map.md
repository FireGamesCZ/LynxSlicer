# PrusaSlicer 2.9.7 → OrcaSlicer settings map

Compared `src/libslic3r/PrintConfig.cpp` of PrusaSlicer 2.9.7 (`stable`, 450d70d) and OrcaSlicer `main` (af5f680, 2026-11-10).

| | Keys |
|---|---|
| PrusaSlicer 2.9.7 | 563 |
| OrcaSlicer | 996 |
| Same key in both | 299 |
| PrusaSlicer only | 264 |

The 264 PrusaSlicer-only keys split into:

| Group | Keys |
|---|---|
| Renamed in Orca, same purpose | 122 |
| Renamed, behaves differently | 40 |
| Missing in Orca (FFF) | 39 |
| SLA only | 34 |
| Not user settings | 29 |

**How reliable this is.** The split was done by hand from knowledge of both code bases. For every renamed key the Orca target was checked to exist; whether it behaves the same was not tested. "Missing" means no equivalent key was found, not that the slicing behaviour is absent. The 299 keys with the same name were not compared for behaviour either. Verify each key when it is implemented.

## Renamed, same purpose

| PrusaSlicer key | Label | Orca key |
|---|---|---|
| `arc_fitting` | Arc fitting | `enable_arc_fitting` |
| `automatic_infill_combination_max_layer_height` | Automatic infill combination - Max layer height | `infill_combination_max_layer_height` |
| `avoid_crossing_perimeters` | Avoid crossing perimeters | `reduce_crossing_wall` |
| `avoid_crossing_perimeters_max_detour` | Avoid crossing perimeters - Max detour length | `max_travel_detour_distance` |
| `bed_shape` | Bed shape | `printable_area` |
| `before_layer_gcode` | Before layer change G-code | `before_layer_change_gcode` |
| `between_objects_gcode` | Between objects G-code | `printing_by_object_gcode` |
| `bottom_fill_pattern` | Bottom fill pattern | `bottom_surface_pattern` |
| `bottom_solid_layers` | _CONTEXT | `bottom_shell_layers` |
| `bottom_solid_min_thickness` | _CONTEXT | `bottom_shell_thickness` |
| `bridge_flow_ratio` | Bridge flow ratio | `bridge_flow` |
| `brim_separation` | Brim separation gap | `brim_object_gap` |
| `deretract_speed` | Deretraction Speed | `deretraction_speed` |
| `disable_fan_first_layers` | Disable fan for the first | `close_fan_the_first_x_layers` |
| `dont_support_bridges` | Don't support bridges | `bridge_no_support` |
| `enable_dynamic_overhang_speeds` | Enable dynamic overhang speeds | `enable_overhang_speed` |
| `end_filament_gcode` | End G-code | `filament_end_gcode` |
| `end_gcode` | End G-code | `machine_end_gcode` |
| `external_perimeter_acceleration` | External perimeters | `outer_wall_acceleration` |
| `external_perimeter_extrusion_width` | External perimeters | `outer_wall_line_width` |
| `external_perimeter_speed` | External perimeters | `outer_wall_speed` |
| `extrusion_multiplier` | Extrusion multiplier | `filament_flow_ratio` |
| `extrusion_width` | Default extrusion width | `line_width` |
| `fan_below_layer_time` | Enable fan if layer print time is below | `fan_cooling_layer_time` |
| `filament_load_time` | Filament load time | `machine_load_filament_time` |
| `filament_shrinkage_compensation_xy` | Shrinkage compensation XY | `filament_shrink` |
| `filament_unload_time` | Filament unload time | `machine_unload_filament_time` |
| `fill_angle` | Fill angle | `infill_direction` |
| `fill_density` | Fill density | `sparse_infill_density` |
| `fill_pattern` | Fill pattern | `sparse_infill_pattern` |
| `first_layer_acceleration` | First layer | `initial_layer_acceleration` |
| `first_layer_extrusion_width` | First layer | `initial_layer_line_width` |
| `first_layer_height` | First layer height | `initial_layer_print_height` |
| `first_layer_infill_speed` | First layer solid infill speed | `initial_layer_infill_speed` |
| `first_layer_speed` | First layer speed | `initial_layer_speed` |
| `first_layer_temperature` | First layer | `nozzle_temperature_initial_layer` |
| `fuzzy_skin_point_dist` | Fuzzy skin point distance | `fuzzy_skin_point_distance` |
| `gap_fill_speed` | Gap fill | `gap_infill_speed` |
| `gcode_resolution` | G-code resolution | `resolution` |
| `infill_acceleration` | Infill | `sparse_infill_acceleration` |
| `infill_extruder` | Infill extruder | `sparse_infill_filament_id` |
| `infill_extrusion_width` | Infill | `sparse_infill_line_width` |
| `infill_first` | Infill before perimeters | `is_infill_first` |
| `infill_overlap` | Infill/perimeters overlap | `infill_wall_overlap` |
| `infill_speed` | Infill | `sparse_infill_speed` |
| `ironing_flowrate` | Flow rate | `ironing_flow` |
| `layer_gcode` | After layer change G-code | `layer_change_gcode` |
| `max_fan_speed` | Max | `fan_max_speed` |
| `max_print_height` | Max print height | `printable_height` |
| `min_fan_speed` | Min | `fan_min_speed` |
| `min_print_speed` | Min print speed | `slow_down_min_speed` |
| `only_one_perimeter_first_layer` | Only one perimeter on first layer | `only_one_wall_first_layer` |
| `only_retract_when_crossing_perimeters` | Only retract when crossing perimeters | `reduce_infill_retraction` |
| `output_filename_format` | Output filename format | `filename_format` |
| `overhang_speed_0` | speed for 0% overlap (bridge) | `overhang_1_4_speed` |
| `overhang_speed_1` | speed for 25% overlap | `overhang_2_4_speed` |
| `overhang_speed_2` | speed for 50% overlap | `overhang_3_4_speed` |
| `overhang_speed_3` | speed for 75% overlap | `overhang_4_4_speed` |
| `overhangs` | Detect bridging perimeters | `detect_overhang_wall` |
| `pause_print_gcode` | Pause Print G-code | `machine_pause_gcode` |
| `perimeter_acceleration` | Perimeters | `inner_wall_acceleration` |
| `perimeter_extrusion_width` | Perimeters | `inner_wall_line_width` |
| `perimeter_generator` | Perimeter generator | `wall_generator` |
| `perimeter_speed` | Perimeters | `inner_wall_speed` |
| `perimeters` | Perimeters | `wall_loops` |
| `retract_before_travel` | Minimum travel after retraction | `retraction_minimum_travel` |
| `retract_layer_change` | Retract on layer change | `retract_when_changing_layer` |
| `retract_length` | Retraction length | `retraction_length` |
| `retract_lift` | Lift height | `z_hop` |
| `retract_speed` | Retraction Speed | `retraction_speed` |
| `seam_gap_distance` | Seam gap distance | `seam_gap` |
| `skirts` | Loops (minimum) | `skirt_loops` |
| `slowdown_below_layer_time` | Slow down if layer print time is below | `slow_down_layer_time` |
| `solid_infill_acceleration` | Solid infill | `internal_solid_infill_acceleration` |
| `solid_infill_below_area` | Solid infill threshold area | `minimum_sparse_infill_area` |
| `solid_infill_extruder` | Solid infill extruder | `internal_solid_filament_id` |
| `solid_infill_extrusion_width` | Solid infill | `internal_solid_infill_line_width` |
| `solid_infill_speed` | Solid infill | `internal_solid_infill_speed` |
| `spiral_vase` | Spiral vase | `spiral_mode` |
| `start_filament_gcode` | Start G-code | `filament_start_gcode` |
| `start_gcode` | Start G-code | `machine_start_gcode` |
| `support_material` | Generate support material | `enable_support` |
| `support_material_angle` | Pattern angle | `support_angle` |
| `support_material_bottom_contact_distance` | Bottom contact Z distance | `support_bottom_z_distance` |
| `support_material_bottom_interface_layers` | Bottom interface layers | `support_interface_bottom_layers` |
| `support_material_buildplate_only` | Support on build plate only | `support_on_build_plate_only` |
| `support_material_contact_distance` | Top contact Z distance | `support_top_z_distance` |
| `support_material_enforce_layers` | Enforce support for the first | `enforce_support_layers` |
| `support_material_extruder` | Support material/raft/skirt extruder | `support_filament` |
| `support_material_extrusion_width` | Support material | `support_line_width` |
| `support_material_interface_contact_loops` | Interface loops | `support_interface_loop_pattern` |
| `support_material_interface_extruder` | Support material/raft interface extruder | `support_interface_filament` |
| `support_material_interface_layers` | Top interface layers | `support_interface_top_layers` |
| `support_material_interface_pattern` | Interface pattern | `support_interface_pattern` |
| `support_material_interface_spacing` | Interface pattern spacing | `support_interface_spacing` |
| `support_material_interface_speed` | Support material interface | `support_interface_speed` |
| `support_material_pattern` | Pattern | `support_base_pattern` |
| `support_material_spacing` | Pattern spacing | `support_base_pattern_spacing` |
| `support_material_speed` | Support material | `support_speed` |
| `support_material_style` | Style | `support_style` |
| `support_material_threshold` | Overhang threshold | `support_threshold_angle` |
| `support_material_xy_spacing` | XY separation between an object and its support | `support_object_xy_distance` |
| `support_tree_angle_slow` | Preferred Branch Angle | `tree_support_angle_slow` |
| `support_tree_branch_diameter_angle` | Branch Diameter Angle | `tree_support_branch_diameter_angle` |
| `support_tree_tip_diameter` | Tip Diameter | `tree_support_tip_diameter` |
| `support_tree_top_rate` | Branch Density | `tree_support_top_rate` |
| `temperature` | Other layers | `nozzle_temperature` |
| `thin_walls` | Detect thin walls | `detect_thin_wall` |
| `toolchange_gcode` | Tool change G-code | `change_filament_gcode` |
| `top_fill_pattern` | Top fill pattern | `top_surface_pattern` |
| `top_infill_extrusion_width` | Top solid infill | `top_surface_line_width` |
| `top_solid_infill_acceleration` | Top solid infill | `top_surface_acceleration` |
| `top_solid_infill_speed` | Top solid infill | `top_surface_speed` |
| `top_solid_layers` | _CONTEXT | `top_shell_layers` |
| `top_solid_min_thickness` | _CONTEXT | `top_shell_thickness` |
| `wipe_into_infill` | Wipe into this object's infill | `flush_into_infill` |
| `wipe_into_objects` | Wipe into this object | `flush_into_objects` |
| `wipe_tower` | Enable | `enable_prime_tower` |
| `wipe_tower_brim_width` | Wipe tower brim width | `prime_tower_brim_width` |
| `wipe_tower_extruder` | Wipe tower extruder | `wipe_tower_filament` |
| `wipe_tower_width` | Width | `prime_tower_width` |
| `wiping_volumes_matrix` | Purging volumes - matrix | `flush_volumes_matrix` |

## Renamed, behaves differently

| PrusaSlicer key | Label | Orca key | Difference |
|---|---|---|---|
| `automatic_infill_combination` | Automatic infill combination | `infill_combination` | same checkbox as `infill_every_layers` |
| `bed_temperature` | Other layers | `hot_plate_temp` | Orca has one temperature per plate type (`cool_plate_temp`, `textured_plate_temp`, …) |
| `bridge_fan_speed` | Bridges fan speed | `overhang_fan_speed` | shared with overhang fan speed |
| `color_change_gcode` | Color change G-code | `change_filament_gcode` | shared with tool-change G-code |
| `complete_objects` | Complete individual objects | `print_sequence` | enum (by layer / by object) instead of a checkbox |
| `cooling` | Enable auto cooling | `slow_down_for_layer_cooling` | no master switch; closest toggle |
| `enable_dynamic_fan_speeds` | Enable dynamic fan speeds | `overhang_fan_threshold` | single threshold + speed, not four steps |
| `external_perimeters_first` | External perimeters first | `wall_sequence` | enum (inner/outer, outer/inner, inner/outer/inner) |
| `extruder_clearance_height` | Height | `extruder_clearance_height_to_rod` | split into `…_to_rod` and `…_to_lid` |
| `filament_abrasive` | Abrasive material | `required_nozzle_HRC` | required nozzle hardness (HRC) instead of a flag |
| `filament_purge_multiplier` | Purge volume multiplier | `flush_multiplier` | global multiplier, not per filament |
| `first_layer_bed_temperature` | First layer | `hot_plate_temp_initial_layer` | per plate type, as above |
| `gap_fill_enabled` | Fill gaps | `gap_fill_target` | enum (everywhere / top+bottom / nowhere) |
| `infill_every_layers` | Combine infill every | `infill_combination` | checkbox, layer count is automatic |
| `ironing` | Enable ironing | `ironing_type` | merged into the ironing type enum |
| `machine_limits_usage` | How to apply limits | `emit_machine_limits_to_gcode` | checkbox (emit or not); no "use for time estimate only" |
| `max_volumetric_extrusion_rate_slope_negative` | Max volumetric slope negative | `max_volumetric_extrusion_rate_slope` | single symmetric value |
| `max_volumetric_extrusion_rate_slope_positive` | Max volumetric slope positive | `max_volumetric_extrusion_rate_slope` | single symmetric value |
| `nozzle_high_flow` | High flow nozzle | `nozzle_volume_type` | enum (standard / high flow) |
| `perimeter_extruder` | Perimeter extruder | `inner_wall_filament_id` | split into inner and outer wall filament |
| `prefer_clockwise_movements` | Prefer clockwise movements | `wall_direction` | enum (auto / CCW / CW) |
| `remaining_times` | Supports remaining times | `disable_m73` | inverted (`disable_m73`) |
| `scarf_seam_entire_loop` | Scarf joint around entire perimeter | `seam_slope_entire_loop` | different scarf seam implementation |
| `scarf_seam_length` | Scarf joint length | `seam_slope_min_length` | different scarf seam implementation |
| `scarf_seam_max_segment_length` | Max scarf joint segment length | `seam_slope_steps` | different scarf seam implementation |
| `scarf_seam_on_inner_perimeters` | Scarf joint on inner perimeters | `seam_slope_inner_walls` | different scarf seam implementation |
| `scarf_seam_only_on_smooth` | Scarf joint only on smooth perimeters | `seam_slope_conditional` | different scarf seam implementation |
| `scarf_seam_placement` | Scarf joint placement | `seam_slope_type` | different scarf seam implementation |
| `scarf_seam_start_height` | Scarf start height | `seam_slope_start_height` | different scarf seam implementation |
| `support_enforcers_only` | Support only in enforced regions | `support_type` | folded into support type (manual) |
| `support_material_auto` | Auto generated supports | `support_type` | folded into support type (normal/tree × auto/manual) |
| `support_material_synchronize_layers` | Synchronize with object layers | `independent_support_layer_height` | inverted meaning |
| `support_tree_angle` | Maximum Branch Angle | `tree_support_branch_angle_organic` | separate keys for organic and classic tree supports |
| `support_tree_branch_diameter` | Branch Diameter | `tree_support_branch_diameter_organic` | separate keys for organic and classic tree supports |
| `support_tree_branch_distance` | Branch Distance | `tree_support_branch_distance_organic` | separate keys for organic and classic tree supports |
| `top_one_perimeter_type` | Single perimeter on top surfaces | `only_one_wall_top` | checkbox, no "topmost only" option |
| `travel_lift_before_obstacle` | Steeper ramp before obstacles | `z_hop_types` | different algorithm |
| `travel_max_lift` | Maximum ramping lift | `z_hop` | different algorithm |
| `travel_ramping_lift` | Use ramping lift | `z_hop_types` | Z-hop type enum (normal / slope / spiral); different algorithm |
| `xy_size_compensation` | XY Size Compensation | `xy_contour_compensation` | split into contour and hole compensation |

## Missing in Orca

Priority is a first guess at how much a PrusaSlicer user would notice.

| PrusaSlicer key | Label | Priority | Note |
|---|---|---|---|
| `binary_gcode` | Supports binary G-code | high | bgcode export; Prusa printers also accept plain G-code |
| `cooling_perimeter_transition_distance` | Perimeter transition distance | high | goes with the above |
| `cooling_slowdown_logic` | Cooling slowdown logic | high | used by current Prusa filament profiles |
| `filament_infill_max_crossing_speed` | Max crossing infill speed | high |  |
| `filament_infill_max_speed` | Max non-crossing infill speed | high | used by current Prusa filament profiles |
| `gcode_substitutions` | G-code substitutions | high | find/replace on generated G-code |
| `overhang_fan_speed_0` | speed for 0% overlap (bridge) | high | dynamic fan speed by overhang, 4 steps |
| `overhang_fan_speed_1` | speed for 25% overlap | high |  |
| `overhang_fan_speed_2` | speed for 50% overlap | high |  |
| `overhang_fan_speed_3` | speed for 75% overlap | high |  |
| `automatic_extrusion_widths` | Automatic extrusion widths calculation | medium |  |
| `avoid_crossing_curled_overhangs` | Avoid crossing curled overhangs (Experimental) | medium |  |
| `extra_perimeters` | Extra perimeters if needed | medium | "extra perimeters if needed" |
| `filament_spool_weight` | Spool weight | medium | covered by the spool inventory |
| `max_print_speed` | Max print speed | medium | auto-speed |
| `max_volumetric_speed` | Max volumetric speed | medium | print-level limit; the filament-level one exists |
| `over_bridge_speed` | Over bridges | medium |  |
| `solid_infill_every_layers` | Solid infill every | medium |  |
| `used_filament_compensation` | Used filament compensation | medium |  |
| `autoemit_temperature_commands` | Emit temperature commands automatically | low |  |
| `custom_parameters_filament` | Custom filament parameters | low |  |
| `custom_parameters_print` | Custom print parameters | low | user variables for custom G-code |
| `custom_parameters_printer` | Custom printer parameters | low |  |
| `extrusion_axis` | Extrusion axis | low |  |
| `fan_always_on` | Keep fan always on | low |  |
| `filament_flush_speed` | Flush speed | low | Orca has `filament_flush_volumetric_speed`; not compared |
| `filament_flush_volume` | Flush volume | low |  |
| `first_layer_acceleration_over_raft` | First object layer over raft interface | low |  |
| `first_layer_speed_over_raft` | Speed of object first layer over raft interface | low |  |
| `multimaterial_purging` | Purging volume | low |  |
| `silent_mode` | Supports stealth mode | low | stealth mode toggle; Orca keeps normal/silent machine limits |
| `support_material_closing_radius` | Closing radius | low |  |
| `support_material_with_sheath` | With sheath around the support | low |  |
| `support_tree_branch_diameter_double_wall` | Branch Diameter with double walls | low |  |
| `travel_short_distance_acceleration` | Travel short distance acceleration | low |  |
| `use_volumetric_e` | Use volumetric E | low |  |
| `variable_layer_height` | Enable variable layer height feature | low | printer capability flag; Orca has the tool itself |
| `wipe_tower_acceleration` | Wipe tower | low |  |
| `wiping_volumes_use_custom_matrix` |  | low |  |

## SLA only

Orca still carries SLA classes in the code; whether SLA printing works there was not checked.

`delay_after_exposure`, `delay_before_exposure`, `delay_to_reflood`, `dynamic_delay_before_profile`, `dynamic_delay_before_timeout`, `dynamic_tilt_down_profile`, `dynamic_tilt_up_profile`, `high_viscosity_tilt_time`, `material_notes`, `material_uuid`, `pad_edge_radius`, `sla_archive_format`, `sla_output_precision`, `support_tree_type`, `tilt_down_cycles`, `tilt_down_delay`, `tilt_down_finish_speed`, `tilt_down_finish_speed_slx`, `tilt_down_initial_speed`, `tilt_down_initial_speed_slx`, `tilt_down_offset_delay`, `tilt_down_offset_steps`, `tilt_up_cycles`, `tilt_up_delay`, `tilt_up_finish_speed`, `tilt_up_finish_speed_slx`, `tilt_up_initial_speed`, `tilt_up_initial_speed_slx`, `tilt_up_offset_delay`, `tilt_up_offset_steps`, `tower_hop_height`, `tower_speed`, `use_tilt`, `zcorrection_layers`

## Not user settings

- Command-line and app options: `colorprint_heights`, `dont_arrange`, `duplicate`, `duplicate_distance`, `loglevel`, `merge`, `save`, `threads`, `webdev`, `single_instance_on_url`, `solid_layers`, `solid_min_thickness`
- Internal preset metadata: `compatible_printers_condition_cummulative`, `compatible_prints_condition_cummulative`, `inherits_cummulative`, `physical_printer_settings_id`, `printer_vendor`, `profile_vendor`, `profile_version`, `machine_max_feedrate_`
- Custom G-code placeholders: `bed_temperature_extruder`, `color_change_extruder`, `next_extruder`, `previous_extruder`, `printing_temperature`, `toolchange_z`
- Obsolete in PrusaSlicer: `infill_only_where_needed`, `seam_preferred_direction`, `seam_preferred_direction_jitter`

## The other direction

Orca has 697 keys that PrusaSlicer 2.9.7 does not. They are not listed here; each needs a place in the PrusaSlicer-style tabs.
