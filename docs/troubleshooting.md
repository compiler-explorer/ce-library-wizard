# Troubleshooting Guide

This guide covers common issues and their solutions when using CE Library Wizard.

## Authentication Issues

### "No GitHub authentication found" warning
**Problem:** The tool cannot find GitHub credentials to create pull requests.

**Solutions:**
1. **Use GitHub CLI (Recommended)**
   ```bash
   gh auth login
   ```
   Follow the prompts to authenticate with GitHub.

2. **Use OAuth authentication**
   ```bash
   ./run.sh --oauth
   ```
   This opens your browser for authentication.

3. **Use environment variable**
   ```bash
   export GITHUB_TOKEN=your_personal_access_token
   ./run.sh
   ```

### "gh: command not found"
**Problem:** GitHub CLI is not installed.

**Solution:** Install GitHub CLI:
```bash
# Ubuntu/Debian
sudo apt-get install gh

# macOS
brew install gh
```

### OAuth authentication fails
**Problem:** Browser doesn't open or authentication doesn't complete.

**Solutions:**
- Ensure port 8745 is not in use by another application
- Check your firewall settings allow localhost connections
- Try using GitHub CLI instead: `gh auth login`

## Library Addition Issues

### "Library version already exists"
**Problem:** The specified version is already in Compiler Explorer.

**Solutions:**
- Check the existing versions in the properties files
- Try adding a different version
- If updating, you may need to modify the existing entry manually

### "Path check failed" or "Install test failed"
**Problem:** The library installation validation failed.

**Solutions:**
1. **Check directory permissions**
   ```bash
   # Create the directory if it doesn't exist
   sudo mkdir -p /opt/compiler-explorer
   sudo chown -R $USER: /opt/compiler-explorer
   ```

2. **Skip installation test**
   ```bash
   # Run without --install-test flag
   ./run.sh --lang=cpp --lib=https://github.com/example/lib --ver=1.0.0
   ```

3. **Check library configuration**
   - Ensure the library has proper build files (CMakeLists.txt, etc.)
   - Verify the GitHub URL is correct and accessible

### "Failed to add library to libraries.yaml"
**Problem:** The ce_install command failed to add the library.

**Solutions:**
- Check that the GitHub URL is valid and accessible
- Verify the version format is correct
- For Fortran libraries, ensure the repository has an `fpm.toml` file
- Check debug output: `./run.sh --debug`

## Repository Access Issues

### Cannot clone repositories
**Problem:** Git clone operations fail.

**Solutions:**
1. **Check internet connection**
   ```bash
   ping github.com
   ```

2. **Verify Git configuration**
   ```bash
   git config --list
   ```

3. **Check SSH keys (if using SSH URLs)**
   ```bash
   ssh -T git@github.com
   ```

4. **Use HTTPS instead of SSH**
   Some networks block SSH. The tool uses HTTPS by default.

### Fork creation fails
**Problem:** Cannot create forks of the CE repositories.

**Solutions:**
- Ensure you're authenticated (see Authentication Issues)
- Check if you already have forks with different names
- Verify your GitHub account has permissions to create forks

## Environment Issues

### "Python 3.12 or higher is required"
**Problem:** Python version is too old.

**Solution:** Update Python:
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install python3.12

# macOS with Homebrew
brew install python@3.12
```

### "make: command not found"
**Problem:** Make is not installed.

**Solution:** Install build tools:
```bash
# Ubuntu/Debian
sudo apt-get install build-essential

# macOS
# Install Xcode Command Line Tools
xcode-select --install
```

### Poetry installation fails
**Problem:** The automatic Poetry installation doesn't work.

**Solution:** Install Poetry manually:
```bash
curl -sSL https://install.python-poetry.org | python3 -
export PATH="$HOME/.local/bin:$PATH"
```

## Debugging Tips

### Enable debug mode
Get detailed output about what's happening:
```bash
./run.sh --debug --lang=rust --lib=serde --ver=1.0.195
```

### Check generated files
After running, check the modifications:
```bash
# In the infra repository clone
cat /tmp/ce-lib-wizard-*/infra/bin/yaml/libraries.yaml

# In the main repository clone
cat /tmp/ce-lib-wizard-*/compiler-explorer/etc/config/*.amazon.properties
```

### Verify branch creation
Check that branches were created correctly:
```bash
cd /tmp/ce-lib-wizard-*/infra
git branch -a

cd /tmp/ce-lib-wizard-*/compiler-explorer
git branch -a
```

## Common Error Messages

### "Error: Got unexpected extra argument"
**Problem:** The ce_install command syntax is incorrect.

**Solution:** This is usually a bug in the tool. Please report it with:
- The exact command you ran
- The full error message
- The debug output (`--debug` flag)

### "Failed to generate properties"
**Problem:** Property file generation failed.

**Solutions:**
- Ensure the library was successfully added to libraries.yaml first
- Check that the main repository was cloned successfully
- Verify the properties file exists and is writable

### "No changes to commit"
**Problem:** The library/version combination already exists.

**Solution:** This is not an error - it means the library is already configured. To update:
- Use a different version
- Or manually edit the configuration files

## Getting Help

If these solutions don't resolve your issue:

1. **Run with debug mode** and save the output:
   ```bash
   ./run.sh --debug [your options] > debug.log 2>&1
   ```

2. **Create an issue** at: https://github.com/compiler-explorer/ce-lib-wizard/issues
   Include:
   - The command you ran
   - The error message
   - The debug.log file
   - Your operating system and Python version