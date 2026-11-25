#include "GuidanceTemplate.hpp"

#include <lib/geo/geo.h>
#include <lib/mathlib/mathlib.h>
#include <lib/matrix/matrix/math.hpp>
#include <px4_platform_common/log.h>

ModuleBase::Descriptor GuidanceTemplate::desc{task_spawn, custom_command, print_usage};

GuidanceTemplate::GuidanceTemplate() : ScheduledWorkItem(MODULE_NAME, px4::wq_configurations::nav_and_controllers) {}

bool GuidanceTemplate::init()
{
	ScheduleOnInterval(PERIOD);
	return true;
}

void GuidanceTemplate::guidance(float seconds_in_offboard, float course, float ground_speed, float &lateral_accel,
			   float &altitude_amsl)
{
	// --- the algorithm (replace this) -------------------------------------------------------------------------
	_course_target = matrix::wrap_pi(_course0 + (seconds_in_offboard >= COURSE_STEP_AT ? math::radians(COURSE_STEP_DEG) : 0.f));
	_altitude_target = _altitude0 + (seconds_in_offboard >= ALTITUDE_STEP_AT ? ALTITUDE_STEP_M : 0.f);
	const float limit = CONSTANTS_ONE_G * tanf(math::radians(BANK_LIMIT_DEG));
	lateral_accel = math::constrain(ground_speed * COURSE_GAIN * matrix::wrap_pi(_course_target - course), -limit, limit);
	altitude_amsl = _altitude_target;
	// -----------------------------------------------------------------------------------------------------------
}

void GuidanceTemplate::Run()
{
	if (should_exit()) {
		ScheduleClear();
		exit_and_cleanup(desc);
		return;
	}

	vehicle_status_s status;

	if (_status_sub.update(&status)) {
		_nav_state = status.nav_state;
	}

	_local_position_sub.update(&_position);
	const hrt_abstime now = hrt_absolute_time();
	const bool position_ok = _position.timestamp > 0 && now - _position.timestamp < POSITION_TIMEOUT
				 && _position.v_xy_valid && _position.z_valid && _position.z_global;

	if (!position_ok) {
		// No offboard signal: PX4 will not enter OFFBOARD, and leaves it through its offboard-loss failsafe.
		if (_active) {
			PX4_WARN("guidance_template: local position not valid, offboard signal stopped");
		}

		_active = false;
		return;
	}

	// The offboard signal: which layers this module takes over (velocity = guidance only, see control_mode.cpp).
	offboard_control_mode_s mode{};
	mode.timestamp = now;
	mode.velocity = true;
	_offboard_pub.publish(mode);

	const float course = atan2f(_position.vy, _position.vx);
	const float ground_speed = sqrtf(_position.vx * _position.vx + _position.vy * _position.vy);
	const float altitude = -_position.z + _position.ref_alt;

	if (_nav_state != vehicle_status_s::NAVIGATION_STATE_OFFBOARD) {
		if (_active) {
			PX4_INFO("guidance_template: left OFFBOARD after %.1f s", (double)((now - _entered) * 1e-6));
		}

		_active = false;
		return;
	}

	if (!_active) {
		_active = true;
		_entered = now;
		_course0 = course;
		_altitude0 = altitude;
		_entries++;
		PX4_INFO("guidance_template: OFFBOARD entered, course %.1f deg, altitude %.1f m", (double)math::degrees(course),
			 (double)altitude);
	}

	float lateral_accel = 0.f;
	float altitude_amsl = altitude;
	guidance((now - _entered) * 1e-6f, course, ground_speed, lateral_accel, altitude_amsl);

	fixed_wing_lateral_setpoint_s lateral{};
	lateral.timestamp = now;
	lateral.course = NAN;
	lateral.airspeed_direction = NAN;
	lateral.lateral_acceleration = lateral_accel;
	_lateral_pub.publish(lateral);

	fixed_wing_longitudinal_setpoint_s longitudinal{};
	longitudinal.timestamp = now;
	longitudinal.altitude = altitude_amsl;
	longitudinal.height_rate = NAN;
	longitudinal.equivalent_airspeed = NAN;  // the default airspeed (FW_AIRSPD_TRIM)
	longitudinal.pitch_direct = NAN;
	longitudinal.throttle_direct = NAN;
	_longitudinal_pub.publish(longitudinal);
}

int GuidanceTemplate::task_spawn(int argc, char *argv[])
{
	GuidanceTemplate *instance = new GuidanceTemplate();

	if (instance) {
		desc.object.store(instance);
		desc.task_id = task_id_is_work_queue;

		if (instance->init()) {
			return PX4_OK;
		}

	} else {
		PX4_ERR("alloc failed");
	}

	delete instance;
	desc.object.store(nullptr);
	desc.task_id = -1;
	return PX4_ERROR;
}

int GuidanceTemplate::print_status()
{
	PX4_INFO("%s, OFFBOARD entries %u, course target %.1f deg, altitude target %.1f m", _active ? "active" : "idle",
		 (unsigned)_entries, (double)math::degrees(_course_target), (double)_altitude_target);
	return 0;
}

int GuidanceTemplate::custom_command(int argc, char *argv[])
{
	return print_usage("unknown command");
}

int GuidanceTemplate::print_usage(const char *reason)
{
	if (reason) {
		PX4_WARN("%s\n", reason);
	}

	PRINT_MODULE_DESCRIPTION(
		R"DESCR_STR(
### Description
Example module: guidance in OFFBOARD from inside the firmware (course P law -> lateral acceleration, altitude
hold); PX4's own altitude/speed, attitude and rate control below. Example only; see modules/src/guidance_template/README.md.
)DESCR_STR");

	PRINT_MODULE_USAGE_NAME("guidance_template", "template");
	PRINT_MODULE_USAGE_COMMAND("start");
	PRINT_MODULE_USAGE_DEFAULT_COMMANDS();
	return 0;
}

extern "C" __EXPORT int guidance_template_main(int argc, char *argv[])
{
	return ModuleBase::main(GuidanceTemplate::desc, argc, argv);
}
