// The byte stream to PX4: a TCP server that PX4 SITL's simulator_mavlink connects to, or (HITL) the flight
// controller's serial port. MAVLink framing on top.
#pragma once

#include <chrono>
#include <cstdint>
#include <functional>
#include <string>
#include <vector>

#include "mavlink_types.hpp"

namespace simhost {

class Link {
 public:
  // SITL: listen on `port` and wait up to `accept_timeout_s` for PX4 to connect.
  static Link tcp_server(int port, double accept_timeout_s);
  // HITL: open a serial device in raw mode.
  static Link serial(const std::string &device, int baud);
  // UDP on 127.0.0.1: bound to local_port, sending to remote_port (PX4's simulator_mavlink -u, or a MAVLink instance).
  static Link udp(int local_port, int remote_port);
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
  // Read what is waiting (the descriptor polled readable) and hand every complete message to on_message.
  void pump(const std::function<void(const mavlink_message_t &)> &on_message);
  // Hand the messages already buffered to on_message.
  void drain(const std::function<void(const mavlink_message_t &)> &on_message);
  int fd() const { return fd_; }
  const std::string &description() const { return description_; }

 private:
  Link(int fd, std::string description, int channel = 0)
      : fd_(fd), description_(std::move(description)), channel_(channel) {}
  int fd_ = -1;
  std::string description_;
  int channel_ = 0;  // MAVLink parser channel: one per link
  mavlink_status_t status_{};
  uint8_t buffer_[2048];
  int buffered_ = 0, read_pos_ = 0;
};

// The flight controller's MAVLink belongs to simhost (HITL: its serial port; SITL: its MAVLink UDP link), so every
// other MAVLink user (a flight script, a pilot, a ground station) reaches it through this UDP relay: messages from the
// flight controller go to every peer that sent a datagram in the last kPeerTimeout, and datagrams from a peer go to
// the flight controller unchanged.
class Relay {
 public:
  explicit Relay(int port);
  ~Relay();
  int fd() const { return fd_; }
  void to_peers(const mavlink_message_t &msg);
  // Read one datagram from a peer into `buf`; returns its length (0 if none).
  size_t from_peer(uint8_t *buf, size_t cap);

 private:
  struct Peer {
    unsigned char addr[16];
    std::chrono::steady_clock::time_point seen;
  };
  static constexpr std::chrono::seconds kPeerTimeout{10};
  int fd_ = -1;
  std::vector<Peer> peers_;
};

}  // namespace simhost
