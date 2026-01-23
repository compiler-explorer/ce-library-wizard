# Advanced Usage Guide

This guide covers advanced features and usage patterns for CE Library Wizard.

## Command-Line Automation

### Batch Processing
Process multiple libraries using shell scripting:

```bash
#!/bin/bash
# add-multiple-libs.sh

libraries=(
    "rust:serde:1.0.195"
    "rust:tokio:1.35.1"
    "cpp:https://github.com/fmtlib/fmt:10.2.1"
)

for lib in "${libraries[@]}"; do
    IFS=':' read -r lang name ver <<< "$lib"
    echo "Adding $lang library $name version $ver..."
    ./run.sh --lang="$lang" --lib="$name" --ver="$ver"
done
```

### CI/CD Integration
Use CE Library Wizard in automated workflows:

```yaml
# .github/workflows/add-library.yml
name: Add Library to CE
on:
  workflow_dispatch:
    inputs:
      language:
        required: true
        type: choice
        options: [rust, cpp, fortran]
      library:
        required: true
      version:
        required: true

jobs:
  add-library:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - run: |
          ./run.sh \
            --lang=${{ inputs.language }} \
            --lib=${{ inputs.library }} \
            --ver=${{ inputs.version }} \
            --github-token=${{ secrets.GITHUB_TOKEN }}
```

## Advanced Authentication

### Using GitHub App Tokens
For organizations, you can use GitHub App tokens:

```bash
# Generate app token (example using gh cli extension)
export GITHUB_TOKEN=$(gh app token create --app-id YOUR_APP_ID)
./run.sh --lang=rust --lib=serde --ver=1.0.195
```

### Token Scoping
Minimum required token permissions:
- `repo` - Full repository access (for forking and pushing)
- `workflow` - Update GitHub Actions (if PR includes workflow files)

## Installation Testing Deep Dive

### Understanding --install-test
The `--install-test` flag for C/C++ libraries:

1. **What it does:**
   - Downloads and installs the library locally
   - Verifies installation paths match properties
   - Ensures library can be used by Compiler Explorer

2. **Requirements:**
   ```bash
   # Create and set permissions for CE directory
   sudo mkdir -p /opt/compiler-explorer
   sudo chown -R $USER: /opt/compiler-explorer
   ```

3. **What's checked:**
   - Library downloads successfully
   - Files are placed in expected locations
   - Paths in properties files are correct

### Manual Installation Testing
Test installations manually:

```bash
cd /tmp/ce-lib-wizard-*/infra
poetry run ce_install install "library_id version"
```

## Build Testing Deep Dive

### Understanding --build-test
The `--build-test` flag tests that libraries requiring compilation actually build correctly:

1. **What it does:**
   - Detects installed compilers (gcc, clang) via `ce_install`
   - Runs a dry-run build using the latest compiler
   - Captures all produced artifacts (libraries, headers, pkg-config files)
   - Verifies that expected link libraries match what was built

2. **Requirements:**
   - A compiler must be installed via `ce_install` (e.g., gcc 14.2.0)
   - The infra repository must be cloned

3. **What's checked:**
   - Build completes successfully
   - Expected `.a` files exist for `staticliblink` entries
   - Expected `.so` files exist for `sharedliblink` entries

### Example Output
```
🔨 Running build test... (Build testing available with gcc 15.2.0 (g152))
✓ Build test passed
  Artifacts produced:
  Libraries: libz.a, libz.so, libz.so.1, libz.so.1.3.1
  Headers: zconf.h, zlib.h
  Other: zlib.pc, zlib.3
  Link library verification:
  ✓ -lz (static)
```

### Manual Build Testing
Test builds manually using ce_install:

```bash
cd /opt/compiler-explorer/infra

# List installed compilers
bin/ce_install --filter-match-all list --installed-only --show-compiler-ids --json gcc '!cross'

# Run a build test (dry-run mode, keeps staging directory)
bin/ce_install --debug --dry-run --keep-staging build --temp-install --buildfor g152 'libraries/c++/zlib 1.3.1'

# Check the staging directory for artifacts
ls -la /tmp/ce-cefs-temp/staging/*/install/
```

### Verifying Link Libraries
The build test reads `staticliblink` and `sharedliblink` from `libraries.yaml` and verifies the corresponding library files were produced:

```yaml
# In libraries.yaml
zlib:
  lib_type: static
  staticliblink:
    - z  # Expects libz.a to be built
```

If a library is missing, you'll see:
```
Link library verification:
✗ MISSING -lfoo (static)
⚠️  Missing: libfoo.a
```

## Working with Properties Files

### Understanding Property File Structure

**C++ Properties (`c++.amazon.properties`):**
```properties
libs=fmt:nlohmann_json:boost

libs.fmt.versions=10.2.1:10.2.0:10.1.1
libs.fmt.url.10.2.1=https://github.com/fmtlib/fmt/archive/refs/tags/10.2.1.tar.gz
libs.fmt.path.10.2.1=/opt/compiler-explorer/libs/fmt/10.2.1
```

**Rust Properties (`rust.amazon.properties`):**
```properties
libs=serde:tokio:async-trait

libs.serde.versions=1.0.195:1.0.194
libs.serde.crate=serde
libs.serde.dependencies=serde_derive
```

**Fortran Properties (`fortran.amazon.properties`):**
```properties
libs=json-fortran:roots-fortran

libs.json-fortran.url=https://github.com/jacobwilliams/json-fortran
libs.json-fortran.versions=8.5.0:8.4.0
```

### Manual Property Updates
Sometimes you need manual control:

```python
# Custom property generation
from pathlib import Path

props_file = Path("c++.amazon.properties")
content = props_file.read_text()

# Add new library to libs line
if "libs=" in content:
    content = content.replace("libs=", "libs=mynewlib:", 1)

props_file.write_text(content)
```

## Debugging Techniques

### Verbose Git Operations
```bash
# See all Git commands
export GIT_TRACE=1
export GIT_CURL_VERBOSE=1
./run.sh --debug ...
```

### Inspecting Temporary Files
```bash
# Keep temp directory after exit for debugging
./run.sh --keep-temp --lang=rust --lib=serde --ver=1.0.195

# Find temp directory
ls -la /tmp/ce-lib-wizard-*

# Explore the cloned repositories
cd /tmp/ce-lib-wizard-*/compiler-explorer
ls -la

cd /tmp/ce-lib-wizard-*/infra
ls -la
```

### Manual ce_install Operations
```bash
# Set up environment manually
cd /tmp/ce-lib-wizard-*/infra
make ce

# Run ce_install commands
poetry run ce_install list
poetry run ce_install add-crate serde 1.0.195
```

## Customization Options

### Environment Variables
```bash
# Enable verbose Poetry output
export DEBUG=1
# or
export CE_DEBUG=1

# Use personal access token
export GITHUB_TOKEN=your_token_here

# Custom OAuth app credentials (optional)
export CE_GITHUB_CLIENT_ID=your_client_id
export CE_GITHUB_CLIENT_SECRET=your_client_secret
```

### Custom Fork Names
If you have non-standard fork names:
```bash
# The tool will detect existing forks automatically
# But you can pre-create with custom names:
gh repo fork compiler-explorer/compiler-explorer --clone=false --fork-name=my-ce-fork
```

## Working with Branches


## Advanced Library Configuration

### C++ Library Types
Understanding library type detection:

1. **packaged-headers**: Has CMakeLists.txt
   - Built and installed during CE setup
   - Headers + compiled libraries

2. **header-only**: No CMakeLists.txt
   - Headers copied directly
   - No compilation needed

### Forcing Library Type
Override automatic detection:
```bash
# Force header-only even if CMakeLists.txt exists
./run.sh --lang=cpp --lib=URL --ver=VERSION --type=header-only
```

### Complex Version Patterns
CE supports various version formats:
- Semantic: `1.2.3`, `v1.2.3`
- Date-based: `2024.01.15`
- Git refs: `main`, `develop`
- Commits: `abc123def456`

## Performance Optimization

### Parallel Repository Operations
The tool clones repositories in parallel:
```python
# This happens automatically, but you can verify:
with GitManager() as git_mgr:
    # Both repos clone simultaneously
    main_repo, infra_repo = git_mgr.clone_repositories()
```

### Shallow Clones
The tool uses shallow clones for performance:
```bash
git clone --depth 1 --single-branch
```

## Troubleshooting Complex Scenarios


### Recovering from Partial Runs
If the tool fails partway:
1. Check temp directory for state
2. Manually complete missing steps
3. Or clean up and retry

### Testing Against Local Repositories
For development, test against local clones:
```bash
# Create test repos
mkdir ~/ce-test
cd ~/ce-test
git clone https://github.com/compiler-explorer/compiler-explorer
git clone https://github.com/compiler-explorer/infra

# Modify GitManager to use local paths (development only)
```

## Integration with CE Infrastructure

### Understanding the Build Pipeline
1. PR Created → CI runs tests
2. Maintainer reviews → Approves
3. Merge → Deployment pipeline
4. Library available on compiler-explorer.com

### Testing Your Library
After PRs are merged:
1. Visit https://compiler-explorer.com
2. Select your language
3. Click libraries dropdown
4. Find your library

### Monitoring Deployment
Watch the deployment:
- Check GitHub Actions on the main repo
- Monitor pull request status and CI results

## Best Practices

### Version Selection
- Use stable releases, not development branches
- Prefer tagged versions over commit hashes
- Test the version locally first

### PR Descriptions
Good PR descriptions include:
- Link to library homepage
- Brief description of what it does
- Why it's useful for CE users
- Any special requirements

### Library Naming
- Use lowercase with underscores
- Match the common name of the library
- Be consistent with existing patterns

Remember: The tool handles the complex mechanics, but understanding these advanced features helps you troubleshoot issues and customize behavior for special cases.