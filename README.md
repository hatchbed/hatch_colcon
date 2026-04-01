# Hatchy: Colcon Workspace Management Tool

## Overview

Hatchy is a command-line tool designed to simplify and enhance the management of Colcon workspaces. Inspired by catkin_tools, Hatchy provides a user-friendly interface for working with ROS 2 and other Colcon-based projects.

## Features

Hatchy supports several key commands to streamline your Colcon workspace workflow:

### 1. Build
- Build entire workspaces or specific packages
- Customize build configurations
- Options to build with or without dependencies

```bash
hatchy build                    # Build default workspace
hatchy build --workspace /path  # Build specific workspace
hatchy build --this             # Build package in current directory
hatchy build --no-deps          # Build only specified packages
```

### 2. Clean
- Remove build artifacts
- Clean specific spaces (build, install, test results)
- Support for cleaning packages and their dependents

```bash
hatchy clean                    # Clean default workspace
hatchy clean --build            # Remove build space
hatchy clean --this             # Clean current package
hatchy clean --dependents       # Clean dependent packages
```

### 3. Config
- Configure workspace context
- Manage build spaces and extensions
- Customize build arguments

```bash
hatchy config --extend /path/to/workspace  # Extend another workspace
hatchy config --build-space custom_build   # Set custom build space
```

### 4. Init
- Initialize new Colcon workspaces

```bash
hatchy init                     # Initialize workspace in current directory
hatchy init --workspace /path   # Initialize workspace in specific path
```

### 5. List
- List packages and repositories in workspace

```bash
hatchy list packages            # List all packages
hatchy list repos               # List workspace repositories
```

### 6. Test
- Run tests for workspace or specific packages

```bash
hatchy test                     # Run all tests
hatchy test --this              # Test current package
hatchy test --no-deps           # Test only specified packages
```

## Installation

```bash
pip install git+https://github.com/hatchbed/hatchy
```

## Requirements

- Python 3.7+
- Colcon

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
