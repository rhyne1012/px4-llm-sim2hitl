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

Link::Link(Link &&o) noexcept
    : fd_(o.fd_), description_(std::move(o.description_)), status_(o.status_), buffered_(o.buffered_), read_pos_(o.read_pos_) {
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
      if (mavlink_parse_char(MAVLINK_COMM_0, buffer_[read_pos_++], msg, &status_)) return true;
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

}  // namespace simhost
