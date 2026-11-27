#include "vehicle.hpp"

#include <FGFDMExec.h>
#include <simgear/misc/sg_path.hxx>
#include <simgear/props/props.hxx>

#include <filesystem>
#include <stdexcept>

namespace simhost {
namespace {
constexpr double FT = 0.3048;
constexpr double PSF = 47.880258980336;  // Pa per lbf/ft2
}  // namespace

struct Vehicle::Nodes {
  SGPropertyNode *t, *lat, *lon, *h_sl_m, *h_agl_ft, *vn, *ve, *vd, *phi, *theta, *psi, *pi, *qi, *ri, *fx, *fy, *fz, *mass,
      *p, *T, *qbar, *vt, *alpha, *beta, *wow;
};

Vehicle::Vehicle(const std::string &folder, double dt_s) : fdm_(std::make_unique<JSBSim::FGFDMExec>()), dt_s_(dt_s) {
  namespace fs = std::filesystem;
  const fs::path dir = fs::absolute(folder);
  name_ = dir.filename().string();
  if (!fs::exists(dir / (name_ + ".xml"))) throw std::runtime_error("no " + name_ + ".xml in " + dir.string());
  fdm_->SetDebugLevel(0);
  fdm_->Setdt(dt_s);  // before the model: flight-control components keep the step they are loaded with
  const auto p = [](const fs::path &x) { return SGPath::fromLocal8Bit(x.string().c_str()); };
  if (!fdm_->LoadModel(p(dir.parent_path()), p(dir / "Engines"), p(dir / "Systems"), name_))
    throw std::runtime_error("JSBSim could not load " + dir.string());
  // Adams-Bashforth 2 for all four integrators: higher orders are unstable on stiff ground contact, and JSBSim has
  // no Runge-Kutta. Accuracy comes from the 1 kHz internal step.
  for (const char *k : {"simulation/integrator/rate/rotational", "simulation/integrator/rate/translational",
                        "simulation/integrator/position/rotational", "simulation/integrator/position/translational"})
    set(k, 3);
  n_ = std::make_unique<Nodes>(Nodes{node("simulation/sim-time-sec"), node("position/lat-geod-deg"), node("position/long-gc-deg"),
                                     node("position/h-sl-meters"), node("position/h-agl-ft"), node("velocities/v-north-fps"),
                                     node("velocities/v-east-fps"), node("velocities/v-down-fps"), node("attitude/phi-rad"),
                                     node("attitude/theta-rad"), node("attitude/psi-rad"), node("velocities/pi-rad_sec"),
                                     node("velocities/qi-rad_sec"), node("velocities/ri-rad_sec"), node("forces/fbx-total-lbs"),
                                     node("forces/fby-total-lbs"), node("forces/fbz-total-lbs"), node("inertia/mass-slugs"),
                                     node("atmosphere/P-psf"), node("atmosphere/T-R"), node("aero/qbar-psf"),
                                     node("velocities/vt-fps"), node("aero/alpha-rad"), node("aero/beta-rad"), node("gear/wow")});
}

Vehicle::~Vehicle() = default;

SGPropertyNode *Vehicle::node(const std::string &property) {
  SGPropertyNode *n = fdm_->GetPropertyManager()->GetNode(property, true);
  if (!n) throw std::runtime_error("no property " + property);
  return n;
}

double Vehicle::get(const std::string &property) const { return fdm_->GetPropertyValue(property); }
void Vehicle::set(const std::string &property, double value) { fdm_->SetPropertyValue(property, value); }

void Vehicle::start(double lat_deg, double lon_deg, double agl_m, double heading_deg) {
  set("ic/lat-geod-deg", lat_deg);
  set("ic/long-gc-deg", lon_deg);
  set("ic/terrain-elevation-ft", 0.0);
  set("ic/h-agl-ft", agl_m / FT);
  set("ic/psi-true-deg", heading_deg);
  set("ic/theta-deg", 0.0);
  set("ic/phi-deg", 0.0);
  set("ic/u-fps", 0.0);
  set("ic/v-fps", 0.0);
  set("ic/w-fps", 0.0);
  if (!fdm_->RunIC()) throw std::runtime_error("JSBSim RunIC failed");
  set("propulsion/set-running", -1);
}

bool Vehicle::step(int substeps) {
  for (int i = 0; i < substeps; ++i)
    if (!fdm_->Run()) return false;
  return true;
}

Truth Vehicle::truth() const {
  const Nodes &n = *n_;
  const double m_slug = n.mass->getDoubleValue();
  const auto sf = [&](SGPropertyNode *f) { return f->getDoubleValue() / m_slug * FT; };  // lbf/slug = ft/s2
  Truth t{};
  t.time_s = n.t->getDoubleValue();
  t.lat_deg = n.lat->getDoubleValue();
  t.lon_deg = n.lon->getDoubleValue();
  t.alt_msl_m = n.h_sl_m->getDoubleValue();
  t.alt_agl_m = n.h_agl_ft->getDoubleValue() * FT;
  t.v_ned_m_s[0] = n.vn->getDoubleValue() * FT;
  t.v_ned_m_s[1] = n.ve->getDoubleValue() * FT;
  t.v_ned_m_s[2] = n.vd->getDoubleValue() * FT;
  t.roll_rad = n.phi->getDoubleValue();
  t.pitch_rad = n.theta->getDoubleValue();
  t.yaw_rad = n.psi->getDoubleValue();
  t.rate_inertial_rad_s[0] = n.pi->getDoubleValue();
  t.rate_inertial_rad_s[1] = n.qi->getDoubleValue();
  t.rate_inertial_rad_s[2] = n.ri->getDoubleValue();
  t.specific_force_m_s2[0] = sf(n.fx);
  t.specific_force_m_s2[1] = sf(n.fy);
  t.specific_force_m_s2[2] = sf(n.fz);
  t.pressure_pa = n.p->getDoubleValue() * PSF;
  t.temperature_k = n.T->getDoubleValue() * 5.0 / 9.0;
  t.dynamic_pressure_pa = n.qbar->getDoubleValue() * PSF;
  t.airspeed_m_s = n.vt->getDoubleValue() * FT;
  t.alpha_rad = n.alpha->getDoubleValue();
  t.beta_rad = n.beta->getDoubleValue();
  t.on_ground = n.wow->getDoubleValue() > 0.5;
  return t;
}

}  // namespace simhost
