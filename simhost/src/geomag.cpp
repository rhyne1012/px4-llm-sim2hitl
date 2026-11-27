// Same lookup and bilinear interpolation as PX4's geo_mag_declination.cpp, on PX4's tables.
#include "geomag.hpp"

#include <algorithm>
#include <cmath>

#include "geo_magnetic_tables.hpp"  // from the locked PX4 tree

namespace simhost {
namespace {

unsigned table_index(float *val, float min, float max) {
  *val = std::clamp(*val, min, max - SAMPLING_RES);
  return static_cast<unsigned>((-(min) + *val) / SAMPLING_RES);
}

float table_value(float lat, float lon, const int16_t table[LAT_DIM][LON_DIM]) {
  lat = std::clamp(lat, SAMPLING_MIN_LAT, SAMPLING_MAX_LAT);
  if (lon > SAMPLING_MAX_LON) lon -= 360.f;
  if (lon < SAMPLING_MIN_LON) lon += 360.f;
  float min_lat = std::floor(lat / SAMPLING_RES) * SAMPLING_RES;
  float min_lon = std::floor(lon / SAMPLING_RES) * SAMPLING_RES;
  const unsigned i = table_index(&min_lat, SAMPLING_MIN_LAT, SAMPLING_MAX_LAT);
  const unsigned j = table_index(&min_lon, SAMPLING_MIN_LON, SAMPLING_MAX_LON);
  const float sw = table[i][j], se = table[i][j + 1], ne = table[i + 1][j + 1], nw = table[i + 1][j];
  const float lat_scale = std::clamp((lat - min_lat) / SAMPLING_RES, 0.f, 1.f);
  const float lon_scale = std::clamp((lon - min_lon) / SAMPLING_RES, 0.f, 1.f);
  const float lo = lon_scale * (se - sw) + sw;
  const float hi = lon_scale * (ne - nw) + nw;
  return lat_scale * (hi - lo) + lo;
}

}  // namespace

MagField mag_field(double latitude_deg, double longitude_deg) {
  const float lat = static_cast<float>(latitude_deg), lon = static_cast<float>(longitude_deg);
  return {table_value(lat, lon, declination_table) * WMM_DECLINATION_SCALE_TO_DEGREES,
          table_value(lat, lon, inclination_table) * WMM_INCLINATION_SCALE_TO_DEGREES,
          table_value(lat, lon, totalintensity_table) * WMM_TOTALINTENSITY_SCALE_TO_NANOTESLA * 1e-5};  // nT -> gauss
}

}  // namespace simhost
