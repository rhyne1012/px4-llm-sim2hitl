// The byte stream to PX4: a TCP server that PX4 SITL's simulator_mavlink connects to, or (HITL) the flight
// controller's serial port. MAVLink framing on top.
#pragma once

#include <cstdint>
#include <functional>
#include <string>

#include "mavlink_types.hpp"

namespace simhost {

class Link {
 public:
  // SITL: listen on `port` and wait up to `accept_timeout_s` for PX4 to connect.
  static Link tcp_server(int port, double accept_timeout_s);
  // HITL: open a serial device in raw mode.
  static Link serial(const std::string &device, int baud);
  Link(Link &&other) noexcept;
  ~Link();

  void send(const mavlink_message_t &msg);
  // Wait up to `timeout_s` for the next message; false on timeout. Throws when the peer closes.
  bool receive(mavlink_message_t *msg, double timeout_s);
  // Wait up to `timeout_s`, handing every complete message to `on_message`; when `extra_fd` (>= 0) becomes readable,
  // call `on_extra` and keep waiting. Returns when the time is up.
  void serve(double timeout_s, int extra_fd, const std::function<void(const mavlink_message_t &)> &on_message,
             const std::function<void()> &on_extra);
  void send_raw(const uint8_t *data, size_t n);
  const std::string &description() const { return description_; }

 private:
  Link(int fd, std::string description) : fd_(fd), description_(std::move(description)) {}
  int fd_ = -1;
  std::string description_;
  mavlink_status_t status_{};
  uint8_t buffer_[2048];
  int buffered_ = 0, read_pos_ = 0;
};

// HITL: the flight controller's serial port belongs to simhost, so every other MAVLink user (the test script, a ground
// station) reaches the flight controller through this UDP relay: messages from the flight controller go to the last
// peer that sent a datagram, and datagrams from the peer go to the flight controller unchanged.
class Relay {
 public:
  explicit Relay(int port);
  ~Relay();
  int fd() const { return fd_; }
  void to_peer(const mavlink_message_t &msg);
  // Read one datagram from the peer into `buf`; returns its length (0 if none).
  size_t from_peer(uint8_t *buf, size_t cap);

 private:
  int fd_ = -1;
  bool has_peer_ = false;
  unsigned char peer_[16] = {};
};

}  // namespace simhost
