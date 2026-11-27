// simhost: one vehicle in JSBSim, its avionics, and PX4 over the standard HIL MAVLink messages.
//
//   simhost --vehicle vehicles/testbird --sitl-port 4570 --lockstep --actuator 4:fcs/throttle-cmd-norm:1 ...
//   simhost --vehicle vehicles/testbird --serial /dev/ttyACM0 --baud 2000000 ...           (HITL, real time)
//
// SITL: PX4's simulator_mavlink connects to the TCP port. In lockstep, PX4's clock follows the HIL_SENSOR time and
// each step waits for the HIL_ACTUATOR_CONTROLS that answers it. HITL: the same messages over the flight controller's
// serial port, paced by the wall clock. Out: HIL_SENSOR every step (250 Hz), HIL_GPS every 0.1 s. In: the actuator
// outputs, mapped onto JSBSim properties by --actuator CHANNEL:PROPERTY:GAIN[:OFFSET] (entries for one property add).
// Channels given with --servo-channel go through the servo signal chain first (avionics/servo_chain.h, at the physics
// step), set by --set avionics/servo/{pwm-period-s,pwm-phase-s,delay-s}=VALUE; it is off by default.
// --set PROP=VALUE sets a JSBSim property before the start (configurations: point masses, declared properties, ...);
// --at T:PROP=VALUE sets one when the simulated time reaches T (scenario events such as actuator failures). Both refuse
// a property the vehicle does not have, since JSBSim would create it silently.
//
// A SITL FC with its own startup (a vehicle repository's flight-controller build on the computer, PX4's
// simulator_mavlink in UDP mode): --sitl-udp LOCAL:REMOTE for the simulator link and --mavlink-udp LOCAL:REMOTE for its
// MAVLink instance, whose messages then go to the relay instead of the simulator link's.
// --relay-port N: every other MAVLink user (a flight script, a pilot, a ground station) on UDP 127.0.0.1:N; messages go
// to every peer heard in the last 10 s.
// --simclock FILE / --pilot-sync FILE (lockstep): the simulated time for a pilot process, and the time it lets the
// simulation run to (16 bytes each, two little-endian uint64: ns, then the CLOCK_MONOTONIC ns of the write). simhost
// does not step past the pilot's time while the pilot has written within the last second of wall time.
// --record-property P (repeatable): the properties after the fixed columns of --record (default: the elevator,
// aileron, rudder and throttle positions, thrust and rpm of a conventional JSBSim aircraft, those it has).
#include <algorithm>
#include <csignal>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include <fcntl.h>
#include <sys/mman.h>
#include <poll.h>
#include <unistd.h>

#include <simgear/props/props.hxx>

#include "avionics.hpp"
#include "link.hpp"
#include "servo_chain.h"
#include "vehicle.hpp"

namespace {

volatile std::sig_atomic_t g_stop = 0;
void on_signal(int) { g_stop = 1; }

struct Mapping {
  int channel;
  double gain, offset;
};

struct Event {
  double t;
  std::string property;
  double value;
};

// 16 bytes shared with another process through a mapped file (--simclock, --pilot-sync).
class SharedClock {
 public:
  explicit SharedClock(const std::string &path) {
    fd_ = ::open(path.c_str(), O_RDWR | O_CREAT | O_CLOEXEC, 0644);
    if (fd_ < 0 || ::ftruncate(fd_, 16) < 0) throw std::runtime_error("cannot open " + path);
    void *p = ::mmap(nullptr, 16, PROT_READ | PROT_WRITE, MAP_SHARED, fd_, 0);
    if (p == MAP_FAILED) throw std::runtime_error("cannot map " + path);
    w_ = static_cast<volatile uint64_t *>(p);
    w_[0] = 0;
    w_[1] = 0;
  }
  ~SharedClock() {
    if (w_) ::munmap(const_cast<uint64_t *>(w_), 16);
    if (fd_ >= 0) ::close(fd_);
  }
  void write(uint64_t ns) {
    w_[0] = ns;
    w_[1] = static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
  }
  uint64_t value() const { return w_[0]; }
  uint64_t written_ns() const { return w_[1]; }

 private:
  int fd_ = -1;
  volatile uint64_t *w_ = nullptr;
};

std::pair<int, int> port_pair(const std::string &v) {
  const size_t k = v.find(':');
  if (k == std::string::npos) throw std::invalid_argument(v);
  return {std::stoi(v.substr(0, k)), std::stoi(v.substr(k + 1))};
}

struct Options {
  std::string vehicle, serial, record, extra, simclock, pilot_sync;
  std::pair<int, int> sitl_udp{0, 0}, mavlink_udp{0, 0};
  std::vector<std::string> record_props;
  std::vector<int> servo_channels;
  double servo_period = 0.0, servo_phase = 0.0, servo_delay = 0.0;
  std::vector<Event> events;
  int sitl_port = 0, baud = 2000000, relay_port = 0;
  bool lockstep = false;
  double lat = 22.9100, lon = 120.3110, agl = 0.19, heading = 0.0, duration = 0.0, physics_dt = 0.001, hil_dt = 0.004;
  unsigned seed = 1;
  std::map<std::string, std::vector<Mapping>> actuators;
  std::vector<std::pair<std::string, double>> sets;
};

[[noreturn]] void usage(const char *why) {
  std::fprintf(stderr,
               "%s\nusage: simhost --vehicle DIR (--sitl-port N | --sitl-udp L:R [--mavlink-udp L:R]) [--lockstep [--simclock F --pilot-sync F]]\n"
               "               | --serial DEV [--baud B])\n"
               "               [--actuator CH:PROP:GAIN[:OFFSET]]... [--servo-channel CH]... [--set PROP=VALUE]...\n"
               "               [--at T:PROP=VALUE]... [--lat D --lon D --agl M --heading D]\n"
               "               [--duration S] [--record FILE.csv [--record-property P]...] [--seed N] [--relay-port N]\n",
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
    else if (a == "--sitl-udp") o.sitl_udp = port_pair(next());
    else if (a == "--mavlink-udp") o.mavlink_udp = port_pair(next());
    else if (a == "--simclock") o.simclock = next();
    else if (a == "--pilot-sync") o.pilot_sync = next();
    else if (a == "--record-property") o.record_props.push_back(next());
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
    } else if (a == "--servo-channel") {
      o.servo_channels.push_back(std::stoi(next()));
    } else if (a == "--set") {
      const std::string v = next();
      const size_t k = v.find('=');
      if (k == std::string::npos) usage(("bad --set " + v).c_str());
      const std::string key = v.substr(0, k);
      const double val = std::stod(v.substr(k + 1));
      if (key == "avionics/servo/pwm-period-s") o.servo_period = val;
      else if (key == "avionics/servo/pwm-phase-s") o.servo_phase = val;
      else if (key == "avionics/servo/delay-s") o.servo_delay = val;
      else if (key.rfind("avionics/", 0) == 0) usage(("unknown avionics setting " + key).c_str());
      else o.sets.emplace_back(key, val);
    } else if (a == "--at") {
      const std::string v = next();
      const size_t c = v.find(':'), k = v.find('=');
      if (c == std::string::npos || k == std::string::npos || k < c) usage(("bad --at " + v).c_str());
      o.events.push_back({std::stod(v.substr(0, c)), v.substr(c + 1, k - c - 1), std::stod(v.substr(k + 1))});
    } else usage(("unknown option " + a).c_str());
  }
  if (o.vehicle.empty()) usage("--vehicle is required");
  if ((o.sitl_port > 0) + (o.sitl_udp.first > 0) + !o.serial.empty() != 1)
    usage("give exactly one of --sitl-port, --sitl-udp and --serial");
  if (o.lockstep && !o.serial.empty()) usage("--lockstep is for SITL");
  if (o.mavlink_udp.first > 0 && o.sitl_udp.first <= 0) usage("--mavlink-udp goes with --sitl-udp");
  if ((!o.simclock.empty() || !o.pilot_sync.empty()) && !o.lockstep) usage("--simclock and --pilot-sync need --lockstep");
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
    for (const auto &[prop, value] : o.sets) {
      if (!vehicle.has(prop)) throw std::runtime_error("--set: the vehicle has no property " + prop);
      vehicle.set(prop, value);
    }
    std::vector<Event> events = o.events;
    std::sort(events.begin(), events.end(), [](const Event &a, const Event &b) { return a.t < b.t; });
    for (const Event &e : events)
      if (!vehicle.has(e.property)) throw std::runtime_error("--at: the vehicle has no property " + e.property);
    size_t next_event = 0;
    vehicle.start(o.lat, o.lon, o.agl, o.heading);

    // Servo signal chain on the servo channels, ticked at the physics step.
    const int n_servo = static_cast<int>(o.servo_channels.size());
    const int servo_cap = std::max(1, static_cast<int>(std::lround(o.servo_delay / o.physics_dt)));
    sc_ticks servo_ticks{1, 0, 0};
    if (sc_ticks_from(o.servo_period, o.servo_phase, o.servo_delay, o.physics_dt, servo_cap, &servo_ticks) != 0)
      throw std::runtime_error("servo chain: period, phase and delay must be whole multiples of the physics step");
    std::vector<double> servo_state(static_cast<size_t>(sc_state_size(n_servo, servo_cap)));
    std::vector<double> servo_in(static_cast<size_t>(n_servo), 0.0), servo_out(static_cast<size_t>(n_servo), 0.0);
    sc_reset(servo_state.data(), n_servo, servo_cap, servo_in.data());
    for (int ch : o.servo_channels)
      if (ch < 0 || ch >= 16) throw std::runtime_error("--servo-channel must be 0..15");

    AvionicsProfile profile;
    profile.seed = o.seed;
    Avionics avionics(profile);

    std::cerr << "simhost: vehicle " << o.vehicle << ", physics " << o.physics_dt * 1e3 << " ms x " << substeps
              << ", HIL " << o.hil_dt * 1e3 << " ms" << (o.lockstep ? ", lockstep" : ", real time") << ", " << o.sets.size()
              << " settings, " << events.size() << " events, servo chain on " << n_servo << " channels (frame "
              << servo_ticks.frame << ", phase " << servo_ticks.phase << ", delay " << servo_ticks.delay << " steps)\n";
    Link link = o.sitl_port > 0 ? Link::tcp_server(o.sitl_port, 120.0)
                : o.sitl_udp.first > 0 ? Link::udp(o.sitl_udp.first, o.sitl_udp.second) : Link::serial(o.serial, o.baud);
    std::cerr << "simhost: simulator link " << link.description() << '\n';
    std::unique_ptr<Link> mav;
    if (o.mavlink_udp.first > 0) {
      mav = std::make_unique<Link>(Link::udp(o.mavlink_udp.first, o.mavlink_udp.second));
      std::cerr << "simhost: MAVLink link " << mav->description() << '\n';
    }
    std::unique_ptr<Relay> relay;
    if (o.relay_port > 0) {
      relay = std::make_unique<Relay>(o.relay_port);
      std::cerr << "simhost: MAVLink relay on UDP 127.0.0.1:" << o.relay_port << '\n';
    }
    std::unique_ptr<SharedClock> simclock, pilot_sync;
    if (!o.simclock.empty()) simclock = std::make_unique<SharedClock>(o.simclock);
    if (!o.pilot_sync.empty()) pilot_sync = std::make_unique<SharedClock>(o.pilot_sync);

    // record: fixed columns, then the record properties (by default those of a conventional JSBSim aircraft it has)
    struct Column {
      std::string name, property;
      double scale;
    };
    std::vector<Column> columns;
    if (o.record_props.empty()) {
      const Column defaults[] = {{"elevator_rad", "fcs/elevator-pos-rad", 1.0}, {"aileron_rad", "fcs/aileron-pos-rad", 1.0},
                                 {"rudder_rad", "fcs/rudder-pos-rad", 1.0}, {"throttle", "fcs/throttle-pos-norm", 1.0},
                                 {"thrust_N", "propulsion/engine/thrust-lbs", 4.4482216152605},
                                 {"rpm", "propulsion/engine/propeller-rpm", 1.0}};
      for (const Column &c : defaults)
        if (vehicle.has(c.property)) columns.push_back(c);
    } else {
      for (const std::string &p : o.record_props) {
        if (!vehicle.has(p)) throw std::runtime_error("--record-property: the vehicle has no property " + p);
        columns.push_back({p, p, 1.0});
      }
    }
    std::ofstream rec;
    if (!o.record.empty()) {
      rec.open(o.record);
      rec << "t_s,lat_deg,lon_deg,alt_msl_m,agl_m,roll_deg,pitch_deg,yaw_deg,p_rad_s,q_rad_s,r_rad_s,airspeed_m_s,alpha_deg,"
             "beta_deg,vn_m_s,ve_m_s,vd_m_s,on_ground,armed";
      for (int c = 0; c < 16; ++c) rec << ",ctrl" << c;
      for (const Column &c : columns) rec << ',' << c.name;
      rec << '\n';
    }

    float controls[16] = {};
    bool armed = false, answered = false;
    uint64_t t_us = 0, last_answer_us = 0;
    long steps = 0, waits_timed_out = 0, waits_interrupted = 0, late_steps = 0;
    double first_timeout_s = -1.0;   // simulated time of the first lockstep wait that timed out
    double max_late_ms = 0.0;
    const int gps_every = static_cast<int>(std::lround(profile.gps_period_s / o.hil_dt));
    auto wall_next = std::chrono::steady_clock::now();
    long pilot_waits = 0;

    // Messages of the simulator link: the actuator outputs; to the relay too unless a MAVLink link carries the rest.
    const auto handle = [&](const mavlink_message_t &m) {
      if (relay && !mav) relay->to_peers(m);
      if (m.msgid != MAVLINK_MSG_ID_HIL_ACTUATOR_CONTROLS) return;
      mavlink_hil_actuator_controls_t a;
      mavlink_msg_hil_actuator_controls_decode(&m, &a);
      std::memcpy(controls, a.controls, sizeof controls);
      armed = (a.mode & MAV_MODE_FLAG_SAFETY_ARMED) != 0;
      answered = true;
      last_answer_us = a.time_usec;
    };
    const auto handle_mav = [&](const mavlink_message_t &m) {
      if (relay) relay->to_peers(m);
    };
    // Serve every link and the relay until `done` (or the time is up); true if done.
    uint8_t dgram[2048];
    const auto service = [&](double timeout_s, const std::function<bool()> &done) {
      const auto deadline = std::chrono::steady_clock::now() + std::chrono::duration<double>(timeout_s);
      for (;;) {
        link.drain(handle);
        if (mav) mav->drain(handle_mav);
        if (done && done()) return true;
        const auto left = std::chrono::duration_cast<std::chrono::microseconds>(deadline - std::chrono::steady_clock::now()).count();
        if (left <= 0 || g_stop) return false;
        pollfd p[3];
        int n = 0, i_mav = -1, i_relay = -1;
        p[n++] = {link.fd(), POLLIN, 0};
        if (mav) { i_mav = n; p[n++] = {mav->fd(), POLLIN, 0}; }
        if (relay) { i_relay = n; p[n++] = {relay->fd(), POLLIN, 0}; }
        timespec ts{static_cast<time_t>(left / 1000000), static_cast<long>(left % 1000000) * 1000};
        const int r = ::ppoll(p, static_cast<nfds_t>(n), &ts, nullptr);
        if (r < 0) {
          if (errno == EINTR) continue;
          throw std::runtime_error("poll failed");
        }
        if (r == 0) continue;
        // UDP: an error is the peer's port not open yet (ICMP refused); reading clears it
        if ((p[0].revents & POLLIN) || (link.is_udp() && (p[0].revents & POLLERR))) link.pump(handle);
        else if (p[0].revents & (POLLERR | POLLHUP)) throw std::runtime_error(link.description() + " lost");
        if (i_mav >= 0 && (p[i_mav].revents & (POLLIN | POLLERR))) mav->pump(handle_mav);
        if (i_relay >= 0 && (p[i_relay].revents & POLLIN)) {
          const size_t got = relay->from_peer(dgram, sizeof dgram);
          if (got) (mav ? *mav : link).send_raw(dgram, got);
        }
      }
    };

    while (!g_stop) {
      // lockstep with a pilot: step while the simulated time has not passed the time it allows, so it ends at most one
      // step past it (the pilot wakes once the time reaches its wake-up, which is rarely on the step grid and may round
      // above it: stopping at or before it would leave both waiting), and only while the pilot keeps writing
      if (pilot_sync && answered) {
        const uint64_t now_ns = t_us * 1000;
        const auto pilot_holds = [&]() {
          const uint64_t w = pilot_sync->written_ns();
          if (w == 0 || now_ns <= pilot_sync->value()) return false;
          const uint64_t now = static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
              std::chrono::steady_clock::now().time_since_epoch()).count());
          return now - w < 1000000000ULL;
        };
        if (pilot_holds()) {
          ++pilot_waits;
          while (!g_stop && pilot_holds()) service(0.0005, nullptr);
        }
      }
      while (next_event < events.size() && events[next_event].t <= static_cast<double>(t_us) * 1e-6 + 1e-9) {
        const Event &e = events[next_event++];
        vehicle.set(e.property, e.value);
        std::cerr << "simhost: t " << static_cast<double>(t_us) * 1e-6 << " s: " << e.property << " = " << e.value << '\n';
      }
      for (int sub = 0; sub < substeps; ++sub) {
        double ch[16];
        for (int c = 0; c < 16; ++c) ch[c] = controls[c];
        if (n_servo > 0) {
          for (int j = 0; j < n_servo; ++j) servo_in[static_cast<size_t>(j)] = controls[o.servo_channels[static_cast<size_t>(j)]];
          sc_tick(servo_state.data(), n_servo, servo_cap, &servo_ticks, servo_in.data(), servo_out.data());
          for (int j = 0; j < n_servo; ++j) ch[o.servo_channels[static_cast<size_t>(j)]] = servo_out[static_cast<size_t>(j)];
        }
        for (const Target &tg : targets) {
          double v = 0.0;
          for (const Mapping &m : tg.maps) v += m.gain * ch[m.channel] + m.offset;
          tg.node->setDoubleValue(v);
        }
        if (!vehicle.step(1)) throw std::runtime_error("JSBSim stopped");
      }
      t_us += static_cast<uint64_t>(std::lround(o.hil_dt * 1e6));
      ++steps;
      if (simclock) simclock->write(t_us * 1000);
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
        for (const Column &c : columns) rec << ',' << vehicle.get(c.property) * c.scale;
        rec << '\n';
      }
      if (steps % static_cast<long>(std::lround(5.0 / o.hil_dt)) == 0)
        std::cerr << "simhost: t " << t.time_s << " s, agl " << t.alt_agl_m << " m, airspeed " << t.airspeed_m_s
                  << " m/s, armed " << armed << ", waits timed out " << waits_timed_out << ", late steps " << late_steps
                  << " (max " << max_late_ms << " ms)" << '\n';

      if (o.lockstep && answered) {
        // Lockstep: wait for PX4's answer to this step (its time follows the HIL_SENSOR time).
        if (!service(2.0, [&]() { return last_answer_us >= t_us; })) {
          if (g_stop) {
            ++waits_interrupted;   // a stop request ended the wait: not a missed reply
          } else {
            if (waits_timed_out == 0) first_timeout_s = static_cast<double>(t_us) * 1e-6;
            ++waits_timed_out;
          }
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
        service(left > 0 ? left : 0.0, nullptr);
      }
      if (o.duration > 0 && t.time_s >= o.duration) break;
    }
    std::cerr << "simhost: stopped at " << steps * o.hil_dt << " s simulated, " << waits_timed_out
              << " lockstep waits timed out, " << late_steps << " late steps (max lateness " << max_late_ms << " ms), "
              << pilot_waits << " waits for the pilot\n";
    // One machine-readable line for the runner: the first timeout locates a lockstep problem in simulated time.
    std::cerr << "simhost-summary: {\"simulated_s\": " << steps * o.hil_dt << ", \"lockstep\": " << (o.lockstep ? "true" : "false")
              << ", \"lockstep_waits_timed_out\": " << waits_timed_out << ", \"first_timeout_simulated_s\": "
              << (first_timeout_s < 0 ? std::string("null") : std::to_string(first_timeout_s))
              << ", \"lockstep_waits_ended_by_stop\": " << waits_interrupted << ", \"late_steps\": " << late_steps
              << ", \"max_lateness_ms\": " << max_late_ms << ", \"pilot_waits\": " << pilot_waits << "}\n";
    return 0;
  } catch (const std::exception &e) {
    std::cerr << "simhost: " << e.what() << '\n';
    return 1;
  }
}
