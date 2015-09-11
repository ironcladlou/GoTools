import sublime
import os
import platform
import re
import subprocess
import tempfile

class MergedSettings():
  def __init__(self):
    # This is a Sublime settings object.
    self.plugin = sublime.load_settings("GoTools.sublime-settings")
    # This is just a dict.
    self.project = sublime.active_window().active_view().settings().get('GoTools', {})

  def get(self, key, default = None):
    # Treat empty values as undefined. This is more convenient internally.
    val = self.project.get(key, '')
    if len(str(val)) > 0: return val
    val = self.plugin.get(key, '')
    if len(str(val)) > 0: return val
    return default

class GoToolsSettings():
  def __init__(self):
    if not self.GoEnv:
      raise Exception("GoTools doesn't appear to be initialized")

    # Load the Sublime settings files.
    settings = MergedSettings()

    # Project > Plugin > Shell env > OS env > go env
    self.gopath = settings.get('gopath', self.GoEnv["GOPATH"])
    self.goroot = settings.get('goroot', self.GoEnv["GOROOT"])
    self.ospath = settings.get('path', self.GoEnv["PATH"])

    self.goarch = self.GoEnv["GOHOSTARCH"]
    self.goos = self.GoEnv["GOHOSTOS"]
    self.go_tools = self.GoEnv["GOTOOLDIR"]

    if not self.goroot or not self.goarch or not self.goos or not self.go_tools:
      raise Exception("GoTools couldn't find Go runtime information")

    # The GOROOT bin directory is namespaced with the GOOS and GOARCH.
    self.gorootbin = os.path.join(self.goroot, "bin", self.goos + "_" + self.goarch)

    # Support 'gopath' expansion in project settings.
    if 'gopath' in settings.project:
      sub = settings.plugin.get('gopath', '')
      if len(sub) == 0:
        sub = self.GoEnv['GOPATH']
      self.gopath = settings.project['gopath'].replace('${gopath}', sub)
    
    if self.gopath is None or len(self.gopath) == 0:
      raise Exception("GoTools requires either the `gopath` setting or the GOPATH environment variable to be s")

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

  @staticmethod
  def find_go_binary(path=""):
    goname = "go"
    if platform.system() == "Windows":
      goname = "go.exe"
    for segment in path.split(os.pathsep):
      candidate = os.path.join(segment, goname)
      if os.path.isfile(candidate):
        return candidate
    raise Exception("couldn't find the go binary in path: {0}".format(path))

# Load PATH, GOPATH, GOROOT, and anything `go env` can provide. Use the
# precedence order: Login shell > OS env > go env. All the values are stored
# in GoToolsSettings.GoEnv.
def load_goenv():
  special_keys = ['PATH', 'GOPATH', 'GOROOT']
  env = {}

  # Gather up keys from the OS environment.
  for k in special_keys:
    env[k] = os.getenv(k, '')

  # Hide popups on Windows
  si = None
  if platform.system() == "Windows":
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW

  # For non-Windows platforms, use a login shell to get environment. Write the
  # values to a tempfile; relying on stdout is brittle because of things like
  # ANSI color codes which can come over stdout when .profile/.bashrc are
  # sourced.
  if platform.system() != "Windows":
    for k in special_keys:
      tempf = tempfile.NamedTemporaryFile()
      cmd = [os.getenv("SHELL"), "-l", "-c", "sh -c -l 'echo ${0}>{1}'".format(k, tempf.name)]
      try:
        subprocess.check_output(cmd)
        val = tempf.read().decode("utf-8").rstrip()
        if len(val) > 0:
          env[k] = val
      except subprocess.CalledProcessError as e:
        raise Exception("couldn't resolve environment variable '{0}': {1}".format(k, str(e)))

  if len(env['PATH']) == 0:
    raise Exception("couldn't resolve PATH via system environment or login shell")

  # Resolve the go binary.
  gobinary = GoToolsSettings.find_go_binary(env['PATH'])

  # Gather up the Go environment using `go env`, but only keep keys which
  # aren't already set from the shell or OS environment.
  cmdenv = os.environ.copy()
  for k in env:
    cmdenv[k] = env[k]
  goenv, stderr = subprocess.Popen([gobinary, 'env'], 
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=si, env=cmdenv).communicate()
  if stderr and len(stderr) > 0:
    raise Exception("'{0} env' returned an error: {1}".format(gobinary, stderr.decode()))

  for name in goenv.decode().splitlines():
    match = re.match('(.*)=\"(.*)\"', name)
    if platform.system() == "Windows":
      match = re.match('(?:set\s)(.*)=(.*)', name)
    if match and match.group(1) and match.group(2):
      k = match.group(1)
      v = match.group(2)
      if not k in env or len(env[k]) == 0:
        env[k] = v
  return env

# This is the plugin initialization, which loads required environment
# variables. If this fails, the plugin is basically broken.
#
# TODO: find a better way to inform the user of problems.
try:
  GoToolsSettings.GoEnv = load_goenv()
  print("GoTools: initialized successfully using Go environment: {0}".format(str(GoToolsSettings.GoEnv)))
except Exception as e:
  print("GoTools: ERROR: failed to load environment: {0}".format(str(e)))
  raise e
