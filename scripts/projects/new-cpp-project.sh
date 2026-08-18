#!/bin/bash
set -e

# Check if project name is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <project-name>"
    exit 1
fi

PROJECT_NAME=$1

# Create project directory
mkdir -p "$PROJECT_NAME"
cd "$PROJECT_NAME" || exit

# Create .gitignore
cat > .gitignore <<EOL
.cache/
build/
.aider*
.env
EOL

# Create README
cat > README.md <<EOL
# $PROJECT_NAME

Built with CMake, Ninja, and vcpkg. See build.sh.
EOL

# Create vcpkg manifest
cat > vcpkg.json <<EOL
{
  "dependencies": [
    "fmt",
    "catch2"
  ]
}
EOL

# Create CMakeLists.txt. Split across two heredocs: the first substitutes
# $PROJECT_NAME now, the second is quoted so CMake's own \${...} variable
# references (PROJECT_NAME, CMAKE_SOURCE_DIR, SOURCES) reach the file as
# literal CMake syntax instead of being expanded by this shell.
cat > CMakeLists.txt <<EOF
cmake_minimum_required(VERSION 3.21)
project($PROJECT_NAME CXX)
EOF
cat >> CMakeLists.txt <<'EOF'

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Enable folders for IDEs
set_property(GLOBAL PROPERTY USE_FOLDERS ON)

# Use vcpkg toolchain in superior directory
if(NOT DEFINED CMAKE_TOOLCHAIN_FILE)
  set(CMAKE_TOOLCHAIN_FILE "${CMAKE_SOURCE_DIR}/../vcpkg/scripts/buildsystems/vcpkg.cmake"
      CACHE STRING "")
endif()

# Find required packages
find_package(fmt CONFIG REQUIRED)

# Source files (recursive)
include_directories("${CMAKE_SOURCE_DIR}/src")

# Collect all source and header files recursively
file(GLOB_RECURSE SOURCES CONFIGURE_DEPENDS
    "${CMAKE_SOURCE_DIR}/src/*.cpp"
    "${CMAKE_SOURCE_DIR}/src/*.h"
)

# Create a library from the source files
add_library(${PROJECT_NAME}_lib ${SOURCES})
target_link_libraries(${PROJECT_NAME}_lib PRIVATE fmt::fmt)

# Create the main executable
add_executable(${PROJECT_NAME} ${SOURCES})
target_link_libraries(${PROJECT_NAME} PRIVATE fmt::fmt)

# unit testing
enable_testing()

# Add test source files
file(GLOB_RECURSE TEST_SOURCES CONFIGURE_DEPENDS "${CMAKE_SOURCE_DIR}/tests/*.cpp")

# Define test executable
add_executable(unit_tests ${TEST_SOURCES})

# Link Catch2 and project library
find_package(Catch2 CONFIG REQUIRED)
target_link_libraries(unit_tests PRIVATE
    Catch2::Catch2WithMain
    ${PROJECT_NAME}_lib
)

# Optionally add your src to include path if you're testing internal headers
target_include_directories(unit_tests PRIVATE ${CMAKE_SOURCE_DIR}/src)

# Register with CTest
include(CTest)
include(Catch)
catch_discover_tests(unit_tests)
EOF

# Create source layout: a library-style "module" plus a thin main.cpp,
# mirroring how every feature gets its own src/<module>/ subdirectory.
mkdir -p src/module tests

cat > src/module/hello.h <<'EOF'
#pragma once

#include <string>

void hello(std::string message);
EOF

cat > src/module/hello.cpp <<'EOF'
#include "hello.h"
#include <fmt/core.h>

void hello(std::string message) { fmt::print("Hello, {}!\n", message); }
EOF

cat > src/main.cpp <<'EOF'
#include "module/hello.h"

int main() {
  hello("world");
  return 0;
}
EOF

cat > tests/test_main.cpp <<'EOF'
#define CATCH_CONFIG_MAIN

#include "module/hello.h"
#include <catch2/catch_all.hpp>

TEST_CASE("Example test") { REQUIRE(1 + 1 == 2); }

TEST_CASE("hello") { hello("world"); }
EOF

# Create build script: formats, configures with CMake + Ninja + the vcpkg
# toolchain, builds, runs unit tests, then runs the executable.
cat > build.sh <<EOF
#!/usr/bin/env bash
set -e

PROJECT_NAME=$PROJECT_NAME
EOF
cat >> build.sh <<'EOF'
BUILD_DIR=build

# Format all C++ files using clang-format
echo "Formatting source files..."
find src tests -name '*.cpp' -o -name '*.h' | xargs clang-format -i

# Create build dir
mkdir -p "$BUILD_DIR"

# Configure with CMake + Ninja
cmake -S . -B "$BUILD_DIR" -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE=../vcpkg/scripts/buildsystems/vcpkg.cmake \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON

# Build
cmake --build "$BUILD_DIR"

# unit tests
cd "$BUILD_DIR"
ctest --output-on-failure

# Run
cd ..
echo -e "\n--- Running ---"
"./$BUILD_DIR/$PROJECT_NAME"
EOF
chmod +x build.sh

# This project expects a vcpkg checkout as a sibling directory (see
# CMakeLists.txt / build.sh: ../vcpkg/scripts/buildsystems/vcpkg.cmake).
# Purely informational -- doesn't block scaffolding.
if [ ! -d "../vcpkg" ]; then
    echo ""
    echo "Note: no vcpkg checkout found at ../vcpkg (relative to this project)."
    echo "  git clone https://github.com/microsoft/vcpkg ../vcpkg && ../vcpkg/bootstrap-vcpkg.sh"
fi

# Initialize git
git init

echo "Project $PROJECT_NAME created successfully!"
echo "Run ./build.sh to format, build, test, and run it."

nvim .
