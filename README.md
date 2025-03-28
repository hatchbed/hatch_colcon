# Hatch: Colcon Workspace Management Tool

## Overview

Hatch is a command-line tool designed to simplify and enhance the management of Colcon workspaces. Inspired by catkin_tools, Hatch provides a user-friendly interface for working with ROS 2 and other Colcon-based projects.

## Features

Hatch supports several key commands to streamline your Colcon workspace workflow:

### 1. Build
- Build entire workspaces or specific packages
- Customize build configurations
- Support for build profiles
- Options to build with or without dependencies

```bash
hatch build                    # Build default workspace
hatch build --workspace /path  # Build specific workspace
hatch build --this             # Build package in current directory
hatch build --no-deps          # Build only specified packages
```

### 2. Clean
- Remove build artifacts
- Clean specific spaces (build, install, test results)
- Support for cleaning packages and their dependents

```bash
hatch clean                    # Clean default workspace
hatch clean --build            # Remove build space
hatch clean --this             # Clean current package
hatch clean --dependents       # Clean dependent packages
```

### 3. Config
- Configure workspace context
- Manage build spaces and extensions
- Customize build arguments

```bash
hatch config --extend /path/to/workspace  # Extend another workspace
hatch config --build-space custom_build   # Set custom build space
```

### 4. Init
- Initialize new Colcon workspaces

```bash
hatch init                     # Initialize workspace in current directory
hatch init --workspace /path   # Initialize workspace in specific path
```

### 5. List
- List packages and repositories in workspace

```bash
hatch list packages            # List all packages
hatch list repos               # List workspace repositories
```

### 6. Profile
- Manage multiple build configurations
- Add, remove, and switch between profiles

```bash
hatch profile add my_profile   # Create new profile
hatch profile set my_profile   # Activate profile
hatch profile remove my_profile # Remove profile
```

### 7. Test
- Run tests for workspace or specific packages

```bash
hatch test                     # Run all tests
hatch test --this              # Test current package
hatch test --no-deps           # Test only specified packages
```

## Installation

```bash
# Installation instructions (to be determined)
pip install git+https://github.com/hatchbed/hatch_colcon
```

## Requirements

- Python 3.7+
- Colcon
- argparse

## Contributing

Contributions are welcome! Please submit pull requests or file issues on the project's repository.

## License

BSD 3-Clause License

Copyright (c) 2025, Hatchbed LLC
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

