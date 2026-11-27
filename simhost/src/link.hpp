// The byte stream to PX4: a TCP server that PX4 SITL's simulator_mavlink connects to, or (HITL) the flight
// controller's serial port. MAVLink framing on top.
#pragma once

#include <cstdint>
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
  const std::string &description() const { return description_; }

 private:
  Link(int fd, std::string description) : fd_(fd), description_(std::move(description)) {}
  int fd_ = -1;
  std::string description_;
  mavlink_status_t status_{};
  uint8_t buffer_[2048];
  int buffered_ = 0, read_pos_ = 0;
};

}  // namespace simhost
