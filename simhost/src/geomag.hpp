// Earth magnetic field from PX4's own World Magnetic Model tables (src/lib/world_magnetic_model in the locked PX4
// tree), so the simulated magnetometer agrees with what PX4's estimator expects at the same position.
#pragma once

namespace simhost {

struct MagField {
  double declination_deg;
  double inclination_deg;
  double strength_gauss;
};

MagField mag_field(double latitude_deg, double longitude_deg);

}  // namespace simhost
