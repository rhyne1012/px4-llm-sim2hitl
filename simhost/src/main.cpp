// simhost: one vehicle in JSBSim, its avionics, and PX4 over the standard HIL MAVLink messages.
//
//   simhost --vehicle vehicles/testbird --sitl-port 4570 --lockstep --actuator 4:fcs/throttle-cmd-norm:1 ...
//   simhost --vehicle vehicles/testbird --serial /dev/ttyACM0 --baud 2000000 ...           (HITL, real time)
//
// SITL: PX4's simulator_mavlink connects to the TCP port. In lockstep, PX4's clock follows the HIL_SENSOR time and
// each step waits for the HIL_ACTUATOR_CONTROLS that answers it. HITL: the same messages over the flight controller's
// serial port, paced by the wall clock. Out: HIL_SENSOR every step (250 Hz), HIL_GPS every 0.1 s. In: the actuator
// outputs, mapped onto JSBSim properties by --actuator CHANNEL:PROPERTY:GAIN[:OFFSET] (entries for one property add).
#include <csignal>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include <simgear/props/props.hxx>

#include "avionics.hpp"
#include "link.hpp"
#include "vehicle.hpp"

namespace {

volatile std::sig_atomic_t g_stop = 0;
void on_signal(int) { g_stop = 1; }

struct Mapping {
  int channel;
  double gain, offset;
};

struct Options {
  std::string vehicle, serial, record, extra;
  int sitl_port = 0, baud = 2000000, relay_port = 0;
  bool lockstep = false;
  double lat = 22.9100, lon = 120.3110, agl = 0.19, heading = 0.0, duration = 0.0, physics_dt = 0.001, hil_dt = 0.004;
  unsigned seed = 1;
  std::map<std::string, std::vector<Mapping>> actuators;
  std::vector<std::pair<std::string, double>> sets;
};

[[noreturn]] void usage(const char *why) {
  std::fprintf(stderr,
               "%s\nusage: simhost --vehicle DIR (--sitl-port N [--lockstep] | --serial DEV [--baud B])\n"
               "               [--actuator CH:PROP:GAIN[:OFFSET]]... [--set PROP=VALUE]... [--lat D --lon D --agl M --heading D]\n"
               "               [--duration S] [--record FILE.csv] [--seed N] [--relay-port N (HITL: UDP for other MAVLink users)]\n",
               why);
  std::exit(2);
}

Options parse(int argc, char **argv) {
  Options o;
  for (int i = 1; i < argc; ++i) {
    const std::string a = argv[i];
    const auto next = [&]() -> std::string {
      if (i + 1 >= argc) usage(("missing value after " + a).c_str());
      return argv[++i];
    };
    if (a == "--vehicle") o.vehicle = next();
    else if (a == "--sitl-port") o.sitl_port = std::stoi(next());
    else if (a == "--lockstep") o.lockstep = true;
    else if (a == "--serial") o.serial = next();
    else if (a == "--baud") o.baud = std::stoi(next());
    else if (a == "--relay-port") o.relay_port = std::stoi(next());
    else if (a == "--lat") o.lat = std::stod(next());
    else if (a == "--lon") o.lon = std::stod(next());
    else if (a == "--agl") o.agl = std::stod(next());
    else if (a == "--heading") o.heading = std::stod(next());
    else if (a == "--duration") o.duration = std::stod(next());
    else if (a == "--record") o.record = next();
    else if (a == "--seed") o.seed = static_cast<unsigned>(std::stoul(next()));
    else if (a == "--actuator") {
      const std::string v = next();
      std::vector<std::string> f;
      size_t start = 0;
      for (size_t k; (k = v.find(':', start)) != std::string::npos; start = k + 1) f.push_back(v.substr(start, k - start));
      f.push_back(v.substr(start));
      if (f.size() < 3 || f.size() > 4) usage(("bad --actuator " + v).c_str());
      o.actuators[f[1]].push_back({std::stoi(f[0]), std::stod(f[2]), f.size() == 4 ? std::stod(f[3]) : 0.0});
    } else if (a == "--set") {
      const std::string v = next();
      const size_t k = v.find('=');
      if (k == std::string::npos) usage(("bad --set " + v).c_str());
      o.sets.emplace_back(v.substr(0, k), std::stod(v.substr(k + 1)));
    } else usage(("unknown option " + a).c_str());
  }
  if (o.vehicle.empty()) usage("--vehicle is required");
  if ((o.sitl_port > 0) == !o.serial.empty()) usage("give exactly one of --sitl-port and --serial");
  if (o.lockstep && o.sitl_port <= 0) usage("--lockstep needs --sitl-port");
  return o;
}

}  // namespace

int main(int argc, char **argv) {
  using namespace simhost;
  const Options o = parse(argc, argv);
  std::signal(SIGINT, on_signal);
  std::signal(SIGTERM, on_signal);
  try {
    Vehicle vehicle(o.vehicle, o.physics_dt);
    const int substeps = static_cast<int>(std::lround(o.hil_dt / o.physics_dt));
    struct Target {
      SGPropertyNode *node;
      std::vector<Mapping> maps;
    };
    std::vector<Target> targets;
    for (const auto &[prop, maps] : o.actuators) targets.push_back({vehicle.node(prop), maps});
    vehicle.start(o.lat, o.lon, o.agl, o.heading);
    for (const auto &[prop, value] : o.sets) vehicle.set(prop, value);

    AvionicsProfile profile;
    profile.seed = o.seed;
    Avionics avionics(profile);

    std::cerr << "simhost: vehicle " << o.vehicle << ", physics " << o.physics_dt * 1e3 << " ms x " << substeps
              << ", HIL " << o.hil_dt * 1e3 << " ms" << (o.lockstep ? ", lockstep" : ", real time") << '\n';
    Link link = o.sitl_port > 0 ? Link::tcp_server(o.sitl_port, 120.0) : Link::serial(o.serial, o.baud);
    std::cerr << "simhost: connected on " << link.description() << '\n';

    std::unique_ptr<Relay> relay;
    if (o.relay_port > 0) {
      relay = std::make_unique<Relay>(o.relay_port);
      std::cerr << "simhost: MAVLink relay on UDP 127.0.0.1:" << o.relay_port << '\n';
    }
    std::ofstream rec;
    if (!o.record.empty()) {
      rec.open(o.record);
      rec << "t_s,lat_deg,lon_deg,alt_msl_m,agl_m,roll_deg,pitch_deg,yaw_deg,p_rad_s,q_rad_s,r_rad_s,airspeed_m_s,alpha_deg,"
             "beta_deg,vn_m_s,ve_m_s,vd_m_s,on_ground,armed";
      for (int c = 0; c < 16; ++c) rec << ",ctrl" << c;
      rec << ",elevator_rad,aileron_rad,rudder_rad,throttle,thrust_N,rpm\n";
    }

    float controls[16] = {};
    bool armed = false, answered = false;
    uint64_t t_us = 0, last_answer_us = 0;
    long steps = 0, waits_timed_out = 0, late_steps = 0;
    double max_late_ms = 0.0;
    const int gps_every = static_cast<int>(std::lround(profile.gps_period_s / o.hil_dt));
    auto wall_next = std::chrono::steady_clock::now();
    mavlink_message_t msg;

    const auto handle = [&](const mavlink_message_t &m) {
      if (relay) relay->to_peer(m);
      if (m.msgid != MAVLINK_MSG_ID_HIL_ACTUATOR_CONTROLS) return;
      mavlink_hil_actuator_controls_t a;
      mavlink_msg_hil_actuator_controls_decode(&m, &a);
      std::memcpy(controls, a.controls, sizeof controls);
      armed = (a.mode & MAV_MODE_FLAG_SAFETY_ARMED) != 0;
      answered = true;
      last_answer_us = a.time_usec;
    };

    while (!g_stop) {
      for (const Target &tg : targets) {
        double v = 0.0;
        for (const Mapping &m : tg.maps) v += m.gain * controls[m.channel] + m.offset;
        tg.node->setDoubleValue(v);
      }
      if (!vehicle.step(substeps)) throw std::runtime_error("JSBSim stopped");
      t_us += static_cast<uint64_t>(std::lround(o.hil_dt * 1e6));
      ++steps;
      const Truth t = vehicle.truth();

      mavlink_message_t out;
      const mavlink_hil_sensor_t s = avionics.sensor(t, t_us);
      mavlink_msg_hil_sensor_encode(1, 51, &out, &s);
      link.send(out);
      if (steps % gps_every == 0) {
        const mavlink_hil_gps_t g = avionics.gps(t, t_us);
        mavlink_msg_hil_gps_encode(1, 51, &out, &g);
        link.send(out);
      }

      if (rec.is_open() && steps % 5 == 0) {
        constexpr double D = 180.0 / M_PI;
        rec << t.time_s << ',' << std::setprecision(10) << t.lat_deg << ',' << t.lon_deg << std::setprecision(6) << ','
            << t.alt_msl_m << ',' << t.alt_agl_m << ',' << t.roll_rad * D << ',' << t.pitch_rad * D << ',' << t.yaw_rad * D
            << ',' << t.rate_inertial_rad_s[0] << ',' << t.rate_inertial_rad_s[1] << ',' << t.rate_inertial_rad_s[2] << ','
            << t.airspeed_m_s << ',' << t.alpha_rad * D << ',' << t.beta_rad * D << ',' << t.v_ned_m_s[0] << ','
            << t.v_ned_m_s[1] << ',' << t.v_ned_m_s[2] << ',' << t.on_ground << ',' << armed;
        for (float c : controls) rec << ',' << c;
        rec << ',' << vehicle.get("fcs/elevator-pos-rad") << ',' << vehicle.get("fcs/aileron-pos-rad") << ','
            << vehicle.get("fcs/rudder-pos-rad") << ',' << vehicle.get("fcs/throttle-pos-norm") << ','
            << vehicle.get("propulsion/engine/thrust-lbs") * 4.4482216152605 << ','
            << vehicle.get("propulsion/engine/propeller-rpm") << '\n';
      }
      if (steps % static_cast<long>(std::lround(5.0 / o.hil_dt)) == 0)
        std::cerr << "simhost: t " << t.time_s << " s, agl " << t.alt_agl_m << " m, airspeed " << t.airspeed_m_s
                  << " m/s, armed " << armed << ", waits timed out " << waits_timed_out << ", late steps " << late_steps
                  << " (max " << max_late_ms << " ms)" << '\n';

      if (o.lockstep && answered) {
        // Lockstep: wait for PX4's answer to this step (its time follows the HIL_SENSOR time).
        bool got = false;
        while (!g_stop && !got) {
          if (!link.receive(&msg, 2.0)) {
            ++waits_timed_out;
            break;
          }
          handle(msg);
          got = last_answer_us >= t_us;
        }
      } else {
        // Real time (HITL, or SITL before PX4 first answers): keep the HIL period on the wall clock, serve what comes.
        // A step is late when its sensor message leaves more than one HIL period after its slot.
        const auto now = std::chrono::steady_clock::now();
        if (steps > 1) {
          const double late_ms = std::chrono::duration<double, std::milli>(now - wall_next).count();
          if (late_ms > max_late_ms) max_late_ms = late_ms;
          if (late_ms > o.hil_dt * 1e3) ++late_steps;
        }
        wall_next += std::chrono::microseconds(static_cast<long>(std::lround(o.hil_dt * 1e6)));
        const double left = std::chrono::duration<double>(wall_next - std::chrono::steady_clock::now()).count();
        uint8_t dgram[2048];
        link.serve(left > 0 ? left : 0.0, relay ? relay->fd() : -1, handle, [&]() {
          const size_t n = relay->from_peer(dgram, sizeof dgram);
          if (n) link.send_raw(dgram, n);
        });
      }
      if (o.duration > 0 && t.time_s >= o.duration) break;
    }
    std::cerr << "simhost: stopped at " << steps * o.hil_dt << " s simulated, " << waits_timed_out
              << " lockstep waits timed out, " << late_steps << " late steps (max lateness " << max_late_ms << " ms)\n";
    return 0;
  } catch (const std::exception &e) {
    std::cerr << "simhost: " << e.what() << '\n';
    return 1;
  }
}
