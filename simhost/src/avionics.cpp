#include "avionics.hpp"

#include <cmath>

#include "geomag.hpp"

namespace simhost {
namespace {
constexpr double DEG = M_PI / 180.0;

// Rotate a north-east-down vector into body axes (front-right-down), Euler angles in 3-2-1 order.
void ned_to_body(const double v[3], double roll, double pitch, double yaw, double out[3]) {
  const double cr = std::cos(roll), sr = std::sin(roll), cp = std::cos(pitch), sp = std::sin(pitch), cy = std::cos(yaw),
               sy = std::sin(yaw);
  out[0] = cp * cy * v[0] + cp * sy * v[1] - sp * v[2];
  out[1] = (sr * sp * cy - cr * sy) * v[0] + (sr * sp * sy + cr * cy) * v[1] + sr * cp * v[2];
  out[2] = (cr * sp * cy + sr * sy) * v[0] + (cr * sp * sy - sr * cy) * v[1] + cr * cp * v[2];
}
}  // namespace

Avionics::Avionics(const AvionicsProfile &profile) : p_(profile), rng_(profile.seed) {}

mavlink_hil_sensor_t Avionics::sensor(const Truth &t, uint64_t time_us) {
  mavlink_hil_sensor_t s{};
  s.time_usec = time_us;
  s.xacc = static_cast<float>(t.specific_force_m_s2[0] + noise(p_.accel_noise_m_s2));
  s.yacc = static_cast<float>(t.specific_force_m_s2[1] + noise(p_.accel_noise_m_s2));
  s.zacc = static_cast<float>(t.specific_force_m_s2[2] + noise(p_.accel_noise_m_s2));
  s.xgyro = static_cast<float>(t.rate_inertial_rad_s[0] + noise(p_.gyro_noise_rad_s));
  s.ygyro = static_cast<float>(t.rate_inertial_rad_s[1] + noise(p_.gyro_noise_rad_s));
  s.zgyro = static_cast<float>(t.rate_inertial_rad_s[2] + noise(p_.gyro_noise_rad_s));
  const MagField f = mag_field(t.lat_deg, t.lon_deg);
  const double inc = f.inclination_deg * DEG, dec = f.declination_deg * DEG;
  const double b_ned[3] = {f.strength_gauss * std::cos(inc) * std::cos(dec), f.strength_gauss * std::cos(inc) * std::sin(dec),
                           f.strength_gauss * std::sin(inc)};
  double b[3];
  ned_to_body(b_ned, t.roll_rad, t.pitch_rad, t.yaw_rad, b);
  s.xmag = static_cast<float>(b[0] + noise(p_.mag_noise_gauss));
  s.ymag = static_cast<float>(b[1] + noise(p_.mag_noise_gauss));
  s.zmag = static_cast<float>(b[2] + noise(p_.mag_noise_gauss));
  const double p = t.pressure_pa + noise(p_.baro_noise_pa);
  s.abs_pressure = static_cast<float>(p / 100.0);  // hPa
  s.diff_pressure = static_cast<float>((t.dynamic_pressure_pa + noise(p_.diff_pressure_noise_pa)) / 100.0);
  s.pressure_alt = static_cast<float>(44330.0 * (1.0 - std::pow(p / 101325.0, 0.190295)));
  s.temperature = static_cast<float>(t.temperature_k - 273.15);
  s.fields_updated = 0x1FFF;  // accel, gyro, mag, baro, differential pressure
  s.id = 0;
  return s;
}

mavlink_hil_gps_t Avionics::gps(const Truth &t, uint64_t time_us) const {
  mavlink_hil_gps_t g{};
  g.time_usec = time_us;
  g.fix_type = 3;
  g.lat = static_cast<int32_t>(std::lround(t.lat_deg * 1e7));
  g.lon = static_cast<int32_t>(std::lround(t.lon_deg * 1e7));
  g.alt = static_cast<int32_t>(std::lround(t.alt_msl_m * 1000.0));
  g.eph = static_cast<uint16_t>(p_.gps_eph_m * 100.0);
  g.epv = static_cast<uint16_t>(p_.gps_epv_m * 100.0);
  const double vn = t.v_ned_m_s[0], ve = t.v_ned_m_s[1], vd = t.v_ned_m_s[2];
  const double ground = std::hypot(vn, ve);
  g.vel = static_cast<uint16_t>(std::lround(ground * 100.0));
  g.vn = static_cast<int16_t>(std::lround(vn * 100.0));
  g.ve = static_cast<int16_t>(std::lround(ve * 100.0));
  g.vd = static_cast<int16_t>(std::lround(vd * 100.0));
  double cog = std::atan2(ve, vn) / DEG;
  if (cog < 0) cog += 360.0;
  g.cog = ground > 0.5 ? static_cast<uint16_t>(std::lround(cog * 100.0)) % 36000 : UINT16_MAX;
  g.satellites_visible = 12;
  g.id = 0;
  g.yaw = 0;  // no heading from GPS
  return g;
}

}  // namespace simhost
