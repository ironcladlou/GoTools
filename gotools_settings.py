import sublime
import os
import platform
import re
import subprocess

class MergedSettings():
  def __init__(self):
    # This is a Sublime settings object.
    self.plugin = sublime.load_settings("GoTools.sublime-settings")
    # This is just a dict.
    self.project = sublime.active_window().active_view().settings().get('GoTools', {})

  def get(self, key, default = None):
    return self.project.get(key, self.plugin.get(key, default))

class GoToolsSettings():
  def __init__(self):
    if not self.GoEnv:
      raise Exception("GoTools doesn't appear to be initialized")

    # Load the Sublime settings files.
    settings = MergedSettings()

    self.goroot = self.GoEnv["GOROOT"]
    self.goarch = self.GoEnv["GOHOSTARCH"]
    self.goos = self.GoEnv["GOHOSTOS"]
    self.go_tools = self.GoEnv["GOTOOLDIR"]
    self.ospath = self.GoEnv["OSPATH"]

    if not self.goroot or not self.goarch or not self.goos or not self.go_tools:
      raise Exception("GoTools: ERROR: Couldn't detect Go runtime information from `go env`.")

    # The GOROOT bin directory is namespaced with the GOOS and GOARCH.
    self.gorootbin = os.path.join(self.goroot, "bin", self.goos + "_" + self.goarch)

    # For GOPATH, env < plugin < project, and project supports replacement of
    # ${gopath} with whatever preceded in the hierarchy.
    self.gopath = settings.plugin.get('gopath', os.getenv('GOPATH', ''))
    if len(self.gopath) == 0:
      self.gopath = self.GoEnv['GOPATH']

    if 'gopath' in settings.project:
      self.gopath = settings.project['gopath'].replace('${gopath}', self.gopath)

    if self.gopath is None or len(self.gopath) == 0:
      raise Exception("GoTools: ERROR: You must set either the `gopath` setting or the GOPATH environment variable.")

    # Plugin feature settings.
    self.debug_enabled = settings.get("debug_enabled")
    self.format_on_save = settings.get("format_on_save")
    self.format_backend = settings.get("format_backend")
    self.autocomplete = settings.get("autocomplete")
    self.goto_def_backend = settings.get("goto_def_backend")

    # Project feature settings.
    self.project_package = settings.get("project_package")
    self.build_packages = settings.get("build_packages", [])
    self.test_packages = settings.get("test_packages", [])
    self.tagged_test_tags = settings.get("tagged_test_tags", [])
    self.tagged_test_packages = settings.get("tagged_test_packages", [])
    self.verbose_tests = settings.get("verbose_tests", False)
    self.test_timeout = settings.get("test_timeout", None)

# For Go runtime information, verify go on PATH and ask it about itself.
def load_goenv():
  # Look up the system PATH.
  ospath = os.getenv('PATH', '')
  # For Darwin, get a login shell to resolve PATH as launchd won't always
  # provide it. This technique is borrowed from SublimeFixMacPath[1].
  # [1] https://github.com/int3h/SublimeFixMacPath.
  if platform.system() == "Darwin":
    command = "/usr/bin/login -fqpl $USER $SHELL -l -c 'printf \"%s\" \"$PATH\"'"
    stdout, stderr = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True).communicate()
    if stderr and len(stderr) > 0:
      raise Exception("GoTools: couldn't resolve system PATH: " + stderr.decode())
    ospath = stdout.decode()

  # Find the go binary on PATH, and abort initialization if it can't be found.
  gobinary = None
  goname = "go"
  if platform.system() == "Windows":
    goname = "go.exe"
  for segment in ospath.split(os.pathsep):
    candidate = os.path.join(segment, goname)
    if os.path.isfile(candidate):
      gobinary = candidate
      break
  if not gobinary:
    raise Exception("GoTools: couldn't find the go binary in PATH: " + ospath)

  # Hide popups on Windows
  si = None
  if platform.system() == "Windows":
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW

  # Gather up the Go environment using `go env`.
  print("GoTools: initializing using Go binary: " + gobinary)
  goenv = {}
  goenv["OSPATH"] = ospath
  stdout, stderr = subprocess.Popen([gobinary, 'env'], stdout=subprocess.PIPE, startupinfo=si).communicate()
  if stderr and len(stderr) > 0:
    raise Exception("GoTools: '" + gobinary + " env' failed during initialization: " + stderr.decode())
  for env in stdout.decode().splitlines():
    match = re.match('(.*)=\"(.*)\"', env)
    if platform.system() == "Windows":
      match = re.match('(?:set\s)(.*)=(.*)', env)
    if match and match.group(1) and match.group(2):
      goenv[match.group(1)] = match.group(2)
  return goenv

# Load and keep a cache of the Go runtime information during plugin init.
GoToolsSettings.GoEnv = load_goenv()
print("GoTools: initialized with Go environment: "+str(GoToolsSettings.GoEnv))
