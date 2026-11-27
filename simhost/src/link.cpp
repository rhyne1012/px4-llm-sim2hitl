#include "link.hpp"

#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <sys/socket.h>
#include <termios.h>
#include <unistd.h>

#include <cerrno>
#include <chrono>
#include <cstring>
#include <stdexcept>

namespace simhost {
namespace {
std::runtime_error sys_error(const std::string &what) { return std::runtime_error(what + ": " + std::strerror(errno)); }

speed_t baud_constant(int baud) {
  switch (baud) {
    case 57600: return B57600;
    case 115200: return B115200;
    case 230400: return B230400;
    case 460800: return B460800;
    case 921600: return B921600;
    case 1500000: return B1500000;
    case 2000000: return B2000000;
    default: throw std::runtime_error("unsupported baud rate " + std::to_string(baud));
  }
}
}  // namespace

Link Link::tcp_server(int port, double accept_timeout_s) {
  const int s = ::socket(AF_INET, SOCK_STREAM, 0);
  if (s < 0) throw sys_error("socket");
  const int one = 1;
  ::setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
  sockaddr_in addr{};
  addr.sin_family = AF_INET;
  addr.sin_port = htons(static_cast<uint16_t>(port));
  addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  if (::bind(s, reinterpret_cast<sockaddr *>(&addr), sizeof addr) < 0) {
    ::close(s);
    throw sys_error("bind TCP port " + std::to_string(port));
  }
  ::listen(s, 1);
  pollfd p{s, POLLIN, 0};
  const int r = ::poll(&p, 1, static_cast<int>(accept_timeout_s * 1000));
  if (r <= 0) {
    ::close(s);
    throw std::runtime_error("PX4 did not connect to TCP port " + std::to_string(port) + " within " +
                             std::to_string(static_cast<int>(accept_timeout_s)) + " s");
  }
  const int c = ::accept(s, nullptr, nullptr);
  ::close(s);
  if (c < 0) throw sys_error("accept");
  ::setsockopt(c, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
  return Link(c, "tcp:" + std::to_string(port));
}

Link Link::serial(const std::string &device, int baud) {
  const int fd = ::open(device.c_str(), O_RDWR | O_NOCTTY | O_CLOEXEC);
  if (fd < 0) throw sys_error("open " + device);
  termios tio{};
  if (::tcgetattr(fd, &tio) < 0) {
    ::close(fd);
    throw sys_error("tcgetattr " + device);
  }
  ::cfmakeraw(&tio);
  ::cfsetispeed(&tio, baud_constant(baud));
  ::cfsetospeed(&tio, baud_constant(baud));
  tio.c_cflag |= CLOCAL | CREAD;
  tio.c_cc[VMIN] = 0;
  tio.c_cc[VTIME] = 0;
  if (::tcsetattr(fd, TCSANOW, &tio) < 0) {
    ::close(fd);
    throw sys_error("tcsetattr " + device);
  }
  return Link(fd, "serial:" + device);
}

Link Link::udp(int local_port, int remote_port) {
  const int s = ::socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, 0);
  if (s < 0) throw sys_error("socket");
  sockaddr_in addr{};
  addr.sin_family = AF_INET;
  addr.sin_port = htons(static_cast<uint16_t>(local_port));
  addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  if (::bind(s, reinterpret_cast<sockaddr *>(&addr), sizeof addr) < 0) {
    ::close(s);
    throw sys_error("bind UDP port " + std::to_string(local_port));
  }
  addr.sin_port = htons(static_cast<uint16_t>(remote_port));
  if (::connect(s, reinterpret_cast<sockaddr *>(&addr), sizeof addr) < 0) {
    ::close(s);
    throw sys_error("connect UDP port " + std::to_string(remote_port));
  }
  static int next_channel = 1;  // the parser channel of each UDP link (a second link must not share a parser)
  return Link(s, "udp:" + std::to_string(local_port) + "->" + std::to_string(remote_port), next_channel++);
}

Link::Link(Link &&o) noexcept
    : fd_(o.fd_), description_(std::move(o.description_)), channel_(o.channel_), status_(o.status_), buffered_(o.buffered_),
      read_pos_(o.read_pos_) {
  std::memcpy(buffer_, o.buffer_, sizeof buffer_);
  o.fd_ = -1;
}

Link::~Link() {
  if (fd_ >= 0) ::close(fd_);
}

void Link::send(const mavlink_message_t &msg) {
  uint8_t buf[MAVLINK_MAX_PACKET_LEN];
  const uint16_t n = mavlink_msg_to_send_buffer(buf, &msg);
  size_t done = 0;
  while (done < n) {
    const ssize_t w = ::write(fd_, buf + done, n - done);
    if (w < 0) {
      if (errno == EINTR) continue;
      throw sys_error("write " + description_);
    }
    done += static_cast<size_t>(w);
  }
}

bool Link::receive(mavlink_message_t *msg, double timeout_s) {
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::duration<double>(timeout_s);
  for (;;) {
    while (read_pos_ < buffered_) {
      if (mavlink_parse_char(static_cast<uint8_t>(channel_), buffer_[read_pos_++], msg, &status_)) return true;
    }
    const auto left = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - std::chrono::steady_clock::now()).count();
    pollfd p{fd_, POLLIN, 0};
    const int r = ::poll(&p, 1, left > 0 ? static_cast<int>(left) : 0);
    if (r < 0) {
      if (errno == EINTR) continue;
      throw sys_error("poll " + description_);
    }
    if (r == 0) return false;
    const ssize_t n = ::read(fd_, buffer_, sizeof buffer_);
    if (n == 0) throw std::runtime_error(description_ + " closed by the peer");
    if (n < 0) {
      if (errno == EINTR || errno == EAGAIN) continue;
      throw sys_error("read " + description_);
    }
    buffered_ = static_cast<int>(n);
    read_pos_ = 0;
  }
}

void Link::serve(double timeout_s, int extra_fd, const std::function<void(const mavlink_message_t &)> &on_message,
                 const std::function<void()> &on_extra) {
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::duration<double>(timeout_s);
  mavlink_message_t msg;
  for (;;) {
    while (read_pos_ < buffered_) {
      if (mavlink_parse_char(static_cast<uint8_t>(channel_), buffer_[read_pos_++], &msg, &status_)) on_message(msg);
    }
    const auto left = std::chrono::duration_cast<std::chrono::microseconds>(deadline - std::chrono::steady_clock::now()).count();
    if (left <= 0) return;
    pollfd p[2] = {{fd_, POLLIN, 0}, {extra_fd, POLLIN, 0}};
    timespec ts{static_cast<time_t>(left / 1000000), static_cast<long>(left % 1000000) * 1000};
    const int r = ::ppoll(p, extra_fd >= 0 ? 2 : 1, &ts, nullptr);
    if (r < 0) {
      if (errno == EINTR) continue;
      throw sys_error("poll " + description_);
    }
    if (r == 0) return;
    if (extra_fd >= 0 && (p[1].revents & POLLIN)) on_extra();
    if (p[0].revents & POLLIN) {
      const ssize_t n = ::read(fd_, buffer_, sizeof buffer_);
      if (n == 0) throw std::runtime_error(description_ + " closed by the peer");
      if (n < 0) {
        if (errno == EINTR || errno == EAGAIN) continue;
        throw sys_error("read " + description_);
      }
      buffered_ = static_cast<int>(n);
      read_pos_ = 0;
    } else if (p[0].revents & (POLLERR | POLLHUP)) {
      throw std::runtime_error(description_ + " lost");
    }
  }
}

void Link::drain(const std::function<void(const mavlink_message_t &)> &on_message) {
  mavlink_message_t msg;
  while (read_pos_ < buffered_) {
    if (mavlink_parse_char(static_cast<uint8_t>(channel_), buffer_[read_pos_++], &msg, &status_)) on_message(msg);
  }
}

void Link::pump(const std::function<void(const mavlink_message_t &)> &on_message) {
  drain(on_message);
  const ssize_t n = ::read(fd_, buffer_, sizeof buffer_);
  if (n == 0 && description_.rfind("udp:", 0) != 0) throw std::runtime_error(description_ + " closed by the peer");
  if (n < 0) {
    if (errno == EINTR || errno == EAGAIN || errno == ECONNREFUSED) return;  // UDP: the peer is not there yet
    throw sys_error("read " + description_);
  }
  buffered_ = static_cast<int>(n);
  read_pos_ = 0;
  drain(on_message);
}

void Link::send_raw(const uint8_t *data, size_t n) {
  size_t done = 0;
  while (done < n) {
    const ssize_t w = ::write(fd_, data + done, n - done);
    if (w < 0) {
      if (errno == EINTR) continue;
      throw sys_error("write " + description_);
    }
    done += static_cast<size_t>(w);
  }
}

static_assert(sizeof(sockaddr_in) <= 16, "peer address storage");

Relay::Relay(int port) {
  fd_ = ::socket(AF_INET, SOCK_DGRAM | SOCK_NONBLOCK, 0);
  if (fd_ < 0) throw sys_error("relay socket");
  sockaddr_in addr{};
  addr.sin_family = AF_INET;
  addr.sin_port = htons(static_cast<uint16_t>(port));
  addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  if (::bind(fd_, reinterpret_cast<sockaddr *>(&addr), sizeof addr) < 0) throw sys_error("bind relay UDP port " + std::to_string(port));
}

Relay::~Relay() {
  if (fd_ >= 0) ::close(fd_);
}

void Relay::to_peers(const mavlink_message_t &msg) {
  if (peers_.empty()) return;
  uint8_t buf[MAVLINK_MAX_PACKET_LEN];
  const uint16_t n = mavlink_msg_to_send_buffer(buf, &msg);
  const auto now = std::chrono::steady_clock::now();
  for (const Peer &p : peers_)
    if (now - p.seen < kPeerTimeout) ::sendto(fd_, buf, n, 0, reinterpret_cast<const sockaddr *>(p.addr), sizeof(sockaddr_in));
}

size_t Relay::from_peer(uint8_t *buf, size_t cap) {
  sockaddr_in from{};
  socklen_t len = sizeof from;
  const ssize_t n = ::recvfrom(fd_, buf, cap, 0, reinterpret_cast<sockaddr *>(&from), &len);
  if (n <= 0) return 0;
  const auto now = std::chrono::steady_clock::now();
  bool known = false;
  for (Peer &p : peers_)
    if (std::memcmp(p.addr, &from, sizeof from) == 0) {
      p.seen = now;
      known = true;
    }
  if (!known) {
    Peer p{};
    std::memcpy(p.addr, &from, sizeof from);
    p.seen = now;
    peers_.push_back(p);
  }
  return static_cast<size_t>(n);
}

}  // namespace simhost
