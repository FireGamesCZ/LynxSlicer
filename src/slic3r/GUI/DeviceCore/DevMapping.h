#pragma once

#include <string>
#include <vector>
#include <wx/string.h>

namespace Slic3r { struct FilamentInfo; }

namespace Slic3r
{
//Previous definitions
class MachineObject;

enum MappingOption
{
    USE_LEFT_AMS = 0,
    USE_RIGHT_AMS,
    USE_LEFT_EXT,
    USE_RIGHT_EXT
};

class DevMappingUtil
{
public:
    DevMappingUtil() = delete;
    ~DevMappingUtil() = delete;

public:
    // Name of a printer slot, the same everywhere it is shown to a plug-in: "ext" and "ext2" for the external
    // spools (ids 255 and 254), "ams<ams id>-<tray id>" for everything else (AMS HT included).
    static std::string slot_name(const std::string& ams_id, const std::string& tray_id);

    // The print job's filament -> slot mapping (PrintParams::ams_mapping2: one {ams_id, slot_id} per filament,
    // 0-based, slot_id 255 = not mapped) as a JSON object {"<filament id, 1-based>": slot_name}. Empty string
    // when nothing is mapped or the text is not that array.
    static std::string slot_mapping_json(const std::string& ams_mapping2);

    static bool is_valid_mapping_result(const MachineObject* obj, std::vector<FilamentInfo>& result, bool check_empty_slot = false);

    static int ams_filament_mapping(const MachineObject* obj, const std::vector<FilamentInfo>& filaments, std::vector<FilamentInfo>& result, std::vector<bool> map_opt, std::vector<int> exclude_id = std::vector<int>(), bool nozzle_has_ams_then_ignore_ext = false);
};

};