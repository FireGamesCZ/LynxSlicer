#include "PluginHostBindings.hpp"
#include <pybind11/cast.h>
#include <pybind11/pybind11.h>
#include <pybind11/pytypes.h>

#include <libslic3r/Model.hpp>
#include <libslic3r/PresetBundle.hpp>
#include <libslic3r/AppConfig.hpp>
#include <libslic3r/Semver.hpp>
#include <libslic3r/GCode/GCodeStatistics.hpp>
#include <libslic3r_version.h>
#include <slic3r/GUI/BuildCommit.hpp>
#include <slic3r/GUI/DeviceCore/DevManager.h>
#include <slic3r/GUI/DeviceCore/DevFilaSystem.h>
#include <slic3r/GUI/DeviceManager.hpp>
#include <slic3r/GUI/GUI.hpp>
#include <slic3r/GUI/GUI_App.hpp>
#include <slic3r/GUI/PartPlate.hpp>
#include <slic3r/GUI/OpenGLManager.hpp>
#include <slic3r/GUI/Plater.hpp>
#include <slic3r/Utils/CloudProvider.hpp>
#include <slic3r/Utils/NetworkAgent.hpp>
#include <slic3r/Utils/NetworkAgentFactory.hpp>
#include <slic3r/Utils/bambu_networking.hpp>

#include <boost/algorithm/string/predicate.hpp>
#include <boost/filesystem/path.hpp>
#include <boost/optional/optional.hpp>

#include <memory>
#include <stdexcept>
#include <wx/app.h>
#include <wx/string.h>
#include <wx/thread.h>
#include <string>
#include <utility>

namespace py = pybind11;

namespace Slic3r {
namespace {

GUI::Plater* current_plater()
{
    if (wxTheApp == nullptr)
        throw std::runtime_error("OrcaSlicer application is not initialized");

    GUI::Plater* plater = GUI::wxGetApp().plater();
    if (plater == nullptr)
        throw std::runtime_error("Plater is not available");

    return plater;
}

PresetBundle* current_preset_bundle()
{
    if (wxTheApp == nullptr)
        throw std::runtime_error("OrcaSlicer application is not initialized");

    PresetBundle* preset_bundle = GUI::wxGetApp().preset_bundle;
    if (preset_bundle == nullptr)
        throw std::runtime_error("Preset bundle is not available");

    return preset_bundle;
}

GUI::GUI_App& current_app()
{
    if (wxTheApp == nullptr)
        throw std::runtime_error("OrcaSlicer application is not initialized");
    return GUI::wxGetApp();
}

// The plater and the device list are only safe to touch from the UI thread, and the 3MF export
// renders thumbnails, which needs the UI thread's GL context.
void require_main_thread(const char* function_name)
{
    if (!wxIsMainThread())
        throw std::runtime_error(std::string(function_name) + "() must be called from the UI thread");
}

void export_3mf_copy(GUI::Plater& plater, const std::string& path)
{
    require_main_thread("export_3mf_copy");
    if (!boost::iends_with(path, ".3mf"))
        throw py::value_error("export_3mf_copy() needs a path ending in .3mf");
    // The thumbnails are rendered by the 3D view, which may not exist yet while plugins load.
    if (!GUI::OpenGLManager::get_gl_info().is_detected())
        throw std::runtime_error("export_3mf_copy() needs the 3D view, which is not ready yet");
    // The file is written from C++, so raise the audit event Python's open(path, "w") raises: the
    // plugin gets the same deny list, permissions and prompt as for writing the file itself.
    if (PySys_Audit("open", "ssi", path.c_str(), "w", 0) < 0)
        throw py::error_already_set();
    if (!plater.export_3mf_copy(GUI::into_path(GUI::from_u8(path))))
        throw std::runtime_error("Failed to write " + path);
}

py::object gl_info()
{
    const GUI::OpenGLManager::GLInfo& info = GUI::OpenGLManager::get_gl_info();
    if (!info.is_detected())
        return py::none();
    py::dict out;
    out["vendor"]       = info.get_vendor();
    out["renderer"]     = info.get_renderer();
    out["version"]      = info.get_version();
    out["glsl_version"] = info.get_glsl_version();
    out["core_profile"] = info.is_core_profile();
    return std::move(out);
}

py::dict app_info()
{
    GUI::GUI_App& app = current_app();
    // The app config has no lock of its own; the UI thread is where it is written.
    require_main_thread("app_info");
    py::dict out;
    out["version"]  = SoftFever_VERSION;
    out["build"]    = GUI::build_commit_label;
    out["mode"]     = app.is_editor() ? "editor" : "gcode viewer";
    out["language"] = GUI::into_u8(app.current_language_code_safe());
    // The app config file is deny-listed for plugins; these are the parts a bug report needs.
    const boost::optional<Semver>& config_version = app.last_config_version();
    out["app_config_version"] = config_version && config_version->valid() ? config_version->to_string_sf() : std::string();
    out["stealth_mode"]       = app.app_config != nullptr && app.app_config->get_stealth_mode();
    out["is_signed_in"]       = app.is_user_login(ORCA_CLOUD_PROVIDER);
    out["is_bambu_signed_in"] = app.is_user_login(BBL_CLOUD_PROVIDER);
    out["network_plugin_version"] = NetworkAgent::is_network_module_loaded() ? NetworkAgent::get_version() : std::string();
    const NetworkLibraryLoadError load_error = NetworkAgent::get_load_error();
    out["network_plugin_error"] = load_error.has_error ? load_error.message : std::string();
    return out;
}

py::object selected_printer()
{
    GUI::GUI_App& app = current_app();
    require_main_thread("selected_printer");
    DeviceManager* devices = app.getDeviceManager();
    MachineObject* machine = devices != nullptr ? devices->get_selected_machine() : nullptr;
    if (machine == nullptr)
        return py::none();
    // Agent, model, link and firmware only: no name, serial, address or access code. Other agents
    // fill the model and firmware with placeholders, so those come from Bambu printers only.
    const bool bambu = machine->printer_agent_id == BBL_PRINTER_AGENT_ID;
    py::dict   out;
    out["agent"]      = machine->printer_agent_id;
    out["model_id"]   = bambu ? machine->printer_type : std::string();
    out["connection"] = machine->connection_type();
    out["online"]     = machine->is_online();
    out["connected"]  = machine->is_connected();
    out["firmware"]   = bambu ? machine->get_ota_version() : std::string();
    return std::move(out);
}

// Live state of a printer by dev_id. Only the dev_id the caller passed is echoed: no name, address,
// access code or user id, like selected_printer(). The audit hook judges Python-level events and
// host APIs follow their own contract (see plugin-permissions.md), so there is no permission check.
py::object device_status(const std::string& dev_id)
{
    GUI::GUI_App& app = current_app();
    require_main_thread("device_status");
    DeviceManager* devices = app.getDeviceManager();
    if (devices == nullptr)
        return py::none();
    // get_my_machine covers cloud-bound and LAN printers of the live agent; the selected machine
    // is the fallback for a printer outside that list.
    MachineObject* machine = devices->get_my_machine(dev_id);
    if (machine == nullptr) {
        machine = devices->get_selected_machine();
        if (machine != nullptr && machine->get_dev_id() != dev_id)
            machine = nullptr;
    }
    if (machine == nullptr)
        return py::none();

    py::list trays;
    auto add_tray = [&trays](const std::string& slot, const DevAmsTray& tray) {
        py::dict t;
        t["slot"]       = slot;
        t["type"]       = tray.m_fila_type;
        // The printer reports RRGGBBAA; anything else is not a colour.
        t["color"]      = tray.color.size() == 8 ? "#" + tray.color.substr(0, 6) : std::string();
        t["setting_id"] = tray.setting_id;
        // -1 for an empty slot or when the printer reported no value.
        t["remain"]     = tray.m_fila_type.empty() || tray.remain < 0 ? -1 : tray.remain;
        t["exists"]     = tray.is_exists;
        trays.append(std::move(t));
    };
    if (const std::shared_ptr<DevFilaSystem> fila = machine->GetFilaSystem())
        for (const auto& ams : fila->GetAmsList())
            for (const auto& tray : ams.second->GetTrays())
                add_tray("ams" + ams.first + "-" + tray.first, *tray.second);
    for (const DevAmsTray& tray : machine->vt_slot)
        add_tray(tray.id == std::to_string(VIRTUAL_TRAY_MAIN_ID) ? "ext" : "ext2", tray);

    py::dict out;
    out["state"]        = machine->print_status;
    out["percent"]      = machine->mc_print_percent;
    const bool layers_known = machine->is_support_layer_num && machine->m_layer_num_current;
    out["layer"]        = layers_known && machine->curr_layer > 0 ? py::object(py::int_(machine->curr_layer)) : py::none();
    out["total_layers"] = layers_known && machine->total_layers > 0 ? py::object(py::int_(machine->total_layers)) : py::none();
    out["job_name"]     = machine->subtask_name;
    out["job_id"]       = !machine->job_id_.empty() ? machine->job_id_ : machine->subtask_id_;
    out["gcode_file"]   = machine->m_gcode_file;
    out["print_error"]  = machine->print_error;
    out["trays"]        = std::move(trays);
    return std::move(out);
}

py::object slice_statistics(int plate_index)
{
    GUI::Plater* plater = current_plater();
    require_main_thread("slice_statistics");
    GUI::PartPlateList& plates = plater->get_partplate_list();
    GUI::PartPlate* plate = plate_index < 0 ? plates.get_curr_plate() : plates.get_plate(plate_index);
    if (plate == nullptr)
        throw py::value_error("slice_statistics(): no such plate");
    if (!plate->is_slice_result_valid() || plate->get_slice_result() == nullptr)
        return py::none();
    return py::str(gcode_statistics_json(*plate->get_slice_result()));
}

} // namespace

// Access to the live GUI application: the Plater and the module-level
// plater()/model()/preset_bundle() accessors. Everything here is owned by the
// app and only reachable once the GUI is up (the accessors throw before that).
void host_bindings::register_app(py::module_& host)
{
    py::class_<GUI::Plater, std::unique_ptr<GUI::Plater, py::nodelete>>(host, "Plater")
        .def("model", static_cast<Model& (GUI::Plater::*)()>(&GUI::Plater::model), py::return_value_policy::reference_internal)
        .def("is_project_dirty", &GUI::Plater::is_project_dirty)
        .def("is_presets_dirty", &GUI::Plater::is_presets_dirty)
        .def("inside_snapshot_capture", &GUI::Plater::inside_snapshot_capture)
        // Path the project was last opened from or saved to; empty while it has never been saved.
        .def("project_path", [](GUI::Plater& plater) {
            require_main_thread("project_path");
            return GUI::into_u8(plater.get_project_filename(".3mf"));
        })
        .def("export_3mf_copy", &export_3mf_copy, py::arg("path"),
             "Write the current project, unsaved changes included, to path as a 3MF copy. The project's "
             "file name and saved state are not changed, and the signed-in account is not written as the designer.");

    host.def("plater", &current_plater, py::return_value_policy::reference);
    host.def("model", []() -> Model& {
        return current_plater()->model();
    }, py::return_value_policy::reference);
    host.def("preset_bundle", &current_preset_bundle, py::return_value_policy::reference);
    host.def("app_info", &app_info,
             "The running app: version, build, mode, language, app_config_version (the version that wrote the app config "
             "before this run, empty when there was none), stealth_mode, is_signed_in (Orca Cloud), is_bambu_signed_in (Bambu Cloud), network_plugin_version (empty "
             "when the Bambu network plugin is not loaded) and network_plugin_error (empty unless it failed to load).");
    host.def("gl_info", &gl_info,
             "OpenGL vendor, renderer, version, glsl_version and core_profile of the 3D view; None before it has been created.");
    host.def("selected_printer", &selected_printer,
             "Agent, model_id, connection ('lan' or 'cloud'), online, connected and firmware of the printer selected in the "
             "device list; model_id and firmware are empty for non-Bambu agents. None when none is selected. Print hosts "
             "configured in the printer preset (OctoPrint and the like) are not in the device list.");
    host.def("device_status", &device_status, py::arg("dev_id"),
             "Live state of the printer dev_id, or None when it is unknown: state (as the printer reports it, e.g. IDLE, "
             "RUNNING, PAUSE, FINISH, FAILED), percent, layer and total_layers (None when unknown: layer 0, no layer "
             "support, or the printer was only parsed for key fields), job_name, job_id, gcode_file, print_error and "
             "trays, a list of {slot, type, color ('#RRGGBB' or ''), setting_id, remain (-1 for an empty slot or no reported value), exists}. Slots "
             "are 'ext', 'ext2' and 'ams<ams id>-<tray id>'. Call it from the UI thread.");
    host.def("slice_statistics", &slice_statistics, py::arg("plate_index") = -1,
             "The statistics JSON of the sliced G-code of a plate (-1 for the current plate), or None when the plate has no "
             "valid slice result. Call it from the UI thread.");
}

} // namespace Slic3r
