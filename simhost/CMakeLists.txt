cmake_minimum_required(VERSION 3.16)
project(simhost CXX)

# Inputs:
#   JSBSIM_ROOT  install prefix of the locked JSBSim (include/JSBSim, lib/libJSBSim.a)
#   PX4_ROOT     the locked PX4 source tree (MAVLink message definitions, World Magnetic Model tables)
#   PYTHON       a Python that can import pymavlink (PX4's own copy under src/modules/mavlink/mavlink is used)
set(JSBSIM_ROOT "$ENV{HOME}/.cache/px4-jsbsim-sim2hitl/jsbsim-1.3.3-install" CACHE PATH "JSBSim install prefix")
set(PX4_ROOT "$ENV{HOME}/px4/PX4-Autopilot-v1.18.0" CACHE PATH "PX4 source tree")
find_package(Python3 REQUIRED COMPONENTS Interpreter)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

# MAVLink C headers from the PX4 tree's message definitions, generated with PX4's own pymavlink.
set(MAVLINK_DIR "${PX4_ROOT}/src/modules/mavlink/mavlink")
set(MAVLINK_OUT "${CMAKE_BINARY_DIR}/mavlink")
add_custom_command(
  OUTPUT "${MAVLINK_OUT}/common/mavlink.h"
  COMMAND ${CMAKE_COMMAND} -E env "PYTHONPATH=${MAVLINK_DIR}"
          ${Python3_EXECUTABLE} -m pymavlink.tools.mavgen --lang=C --wire-protocol=2.0 --no-validate --output=${MAVLINK_OUT}
          "${MAVLINK_DIR}/message_definitions/v1.0/common.xml"
  DEPENDS "${MAVLINK_DIR}/message_definitions/v1.0/common.xml"
  COMMENT "mavgen: MAVLink C headers from ${MAVLINK_DIR}")
add_custom_target(mavlink_headers DEPENDS "${MAVLINK_OUT}/common/mavlink.h")

add_executable(simhost src/main.cpp src/vehicle.cpp src/avionics.cpp src/geomag.cpp src/link.cpp)
add_dependencies(simhost mavlink_headers)
target_include_directories(simhost PRIVATE src ../avionics "${MAVLINK_OUT}" "${PX4_ROOT}/src/lib/world_magnetic_model")
target_include_directories(simhost SYSTEM PRIVATE "${JSBSIM_ROOT}/include/JSBSim")
target_compile_options(simhost PRIVATE -Wall -Wextra)
target_link_libraries(simhost PRIVATE "${JSBSIM_ROOT}/lib/libJSBSim.a" dl)
