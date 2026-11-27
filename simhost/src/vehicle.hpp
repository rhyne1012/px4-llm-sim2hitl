// One vehicle: a JSBSim aircraft folder (<name>/<name>.xml, Engines/, Systems/) run by the locked JSBSim.
#pragma once

#include <memory>
#include <string>
#include <utility>
#include <vector>

namespace JSBSim {
class FGFDMExec;
}
class SGPropertyNode;

namespace simhost {

// What the avionics and the record need from the physics, in SI units.
struct Truth {
  double time_s;
  double lat_deg, lon_deg, alt_msl_m, alt_agl_m;
  double v_ned_m_s[3];
  double roll_rad, pitch_rad, yaw_rad;
  double rate_inertial_rad_s[3];  // body axes (FRD), relative to inertial space: what a gyro measures
  double specific_force_m_s2[3];  // body axes (FRD): all forces except gravity, over mass; what an accelerometer measures
  double pressure_pa, temperature_k;
  double dynamic_pressure_pa;     // air-relative, what a pitot-static probe measures
  double airspeed_m_s, alpha_rad, beta_rad;
  bool on_ground;
};

class Vehicle {
 public:
  // `folder` is the vehicle's JSBSim aircraft folder. `dt_s` is JSBSim's internal step.
  Vehicle(const std::string &folder, double dt_s);
  ~Vehicle();

  // Start at rest, `agl_m` above the terrain with the CG, on a heading.
  void start(double lat_deg, double lon_deg, double agl_m, double heading_deg);
  bool step(int substeps);
  Truth truth() const;

  double get(const std::string &property) const;
  void set(const std::string &property, double value);
  // A property node resolved once, for values written every step.
  SGPropertyNode *node(const std::string &property);

 private:
  std::unique_ptr<JSBSim::FGFDMExec> fdm_;
  std::string name_;
  double dt_s_;
  struct Nodes;
  std::unique_ptr<Nodes> n_;
};

}  // namespace simhost
