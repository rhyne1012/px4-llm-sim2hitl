/**
 * guidance_template: an example of one way to put your own algorithm into PX4 (see README.md and AGENTS.md, stage 1).
 *
 * It replaces only the top of the fixed-wing control chain (guidance) while the vehicle is in OFFBOARD:
 *   - it publishes offboard_control_mode itself (velocity = true), the same uORB message that MAVLink or ROS 2
 *     would produce from a companion computer, so no companion computer is needed; Commander then runs
 *     PX4's own altitude/speed (fw_lat_lon_control), attitude and rate control below it;
 *   - in OFFBOARD it publishes fixed_wing_lateral_setpoint (a lateral acceleration from a course P law) and
 *     fixed_wing_longitudinal_setpoint (an altitude; airspeed: the default);
 *   - it stops the offboard signal when the local position is not valid or fresh, so PX4's offboard-loss
 *     failsafe takes over (COM_OF_LOSS_T, COM_OBL_RC_ACT).
 *
 * The algorithm is the one function guidance(); the rest is the frame to copy. The test: from entering OFFBOARD,
 * hold the entry course and altitude, turn the course by COURSE_STEP after COURSE_STEP_AT, climb by
 * ALTITUDE_STEP after ALTITUDE_STEP_AT.
 */
#pragma once

#include <px4_platform_common/module.h>
#include <px4_platform_common/px4_work_queue/ScheduledWorkItem.hpp>
#include <drivers/drv_hrt.h>
#include <uORB/Publication.hpp>
#include <uORB/Subscription.hpp>
#include <uORB/topics/fixed_wing_lateral_setpoint.h>
#include <uORB/topics/fixed_wing_longitudinal_setpoint.h>
#include <uORB/topics/offboard_control_mode.h>
#include <uORB/topics/vehicle_local_position.h>
#include <uORB/topics/vehicle_status.h>

using namespace time_literals;

class GuidanceTemplate : public ModuleBase, public px4::ScheduledWorkItem
{
public:
	static Descriptor desc;

	static constexpr hrt_abstime PERIOD = 40_ms;              // 25 Hz
	static constexpr hrt_abstime POSITION_TIMEOUT = 500_ms;
	static constexpr float COURSE_GAIN = 0.2f;                // [1/s] lateral acceleration = V * gain * course error
	static constexpr float BANK_LIMIT_DEG = 20.f;
	static constexpr float COURSE_STEP_DEG = 30.f;
	static constexpr float COURSE_STEP_AT = 15.f;             // [s] after entering OFFBOARD (the previous mode settles)
	static constexpr float ALTITUDE_STEP_M = 10.f;
	static constexpr float ALTITUDE_STEP_AT = 35.f;           // [s] after entering OFFBOARD

	GuidanceTemplate();
	~GuidanceTemplate() override = default;

	static int task_spawn(int argc, char *argv[]);
	static int custom_command(int argc, char *argv[]);
	static int print_usage(const char *reason = nullptr);

	bool init();
	int print_status() override;

private:
	void Run() override;

	/** The algorithm: course and altitude targets -> lateral acceleration [m/s^2, right +] and altitude [m AMSL]. */
	void guidance(float seconds_in_offboard, float course, float ground_speed, float &lateral_accel,
		      float &altitude_amsl);

	uORB::Subscription _local_position_sub{ORB_ID(vehicle_local_position)};
	uORB::Subscription _status_sub{ORB_ID(vehicle_status)};
	uORB::Publication<offboard_control_mode_s> _offboard_pub{ORB_ID(offboard_control_mode)};
	uORB::Publication<fixed_wing_lateral_setpoint_s> _lateral_pub{ORB_ID(fixed_wing_lateral_setpoint)};
	uORB::Publication<fixed_wing_longitudinal_setpoint_s> _longitudinal_pub{ORB_ID(fixed_wing_longitudinal_setpoint)};

	vehicle_local_position_s _position{};
	uint8_t _nav_state{0};
	bool _active{false};
	hrt_abstime _entered{0};
	float _course0{0.f};
	float _altitude0{0.f};
	float _course_target{0.f};
	float _altitude_target{0.f};
	uint32_t _entries{0};
};
