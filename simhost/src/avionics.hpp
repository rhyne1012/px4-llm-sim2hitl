// The flight controller's sensors, between the physics and PX4: what the IMU, magnetometer, barometer, airspeed
// sensor and GPS would report for a given truth state. Noise is Gaussian with a fixed seed, so runs repeat.
#pragma once

#include <cstdint>
#include <random>

#include "mavlink_types.hpp"
#include "vehicle.hpp"

namespace simhost {

struct AvionicsProfile {
  double accel_noise_m_s2 = 0.05;
  double gyro_noise_rad_s = 0.003;
  double mag_noise_gauss = 0.002;
  double baro_noise_pa = 1.5;
  double diff_pressure_noise_pa = 0.5;
  double gps_period_s = 0.1;
  double gps_eph_m = 0.5, gps_epv_m = 0.8;
  unsigned seed = 1;
};

class Avionics {
 public:
  explicit Avionics(const AvionicsProfile &profile);
  mavlink_hil_sensor_t sensor(const Truth &t, uint64_t time_us);
  mavlink_hil_gps_t gps(const Truth &t, uint64_t time_us) const;
  const AvionicsProfile &profile() const { return p_; }

 private:
  double noise(double sigma) { return sigma > 0 ? sigma * gauss_(rng_) : 0.0; }
  AvionicsProfile p_;
  std::mt19937_64 rng_;
  std::normal_distribution<double> gauss_{0.0, 1.0};
};

}  // namespace simhost
