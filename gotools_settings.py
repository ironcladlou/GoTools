import sublime
import os
import platform
import re
import subprocess
import tempfile
import threading

class GoToolsSettings():
  lock = threading.Lock()
  instance = None

  def __init__(self):
    # Only load the environment once.
    # TODO: Consider doing this during refresh. Environment shouldn't change
    # often and the call can be slow if the login shell has a nontrivial
    # amount of init (e.g. bashrc).
    self.env = self.create_environment()
    # Perform the initial plugin settings load.
    self.refresh()
    # Only refresh plugin settings when they have changed.
    self.plugin_settings.add_on_change("gopath", self.refresh)

  @staticmethod
  def get():
    GoToolsSettings.lock.acquire()
    try:
      if GoToolsSettings.instance is None:
        print("GoTools: initializing settings...")
        GoToolsSettings.instance = GoToolsSettings()
        print("GoTools: successfully initialized settings")
    except Exception as e:
      raise Exception("GoTools: ERROR: failed to initialize settings: {0}".format(str(e)))
    finally:
      GoToolsSettings.lock.release()
    return GoToolsSettings.instance

  # There's no direct access to project settings, so load them from the active
  # view every time. This doesn't seem ideal.
  @property
  def project_settings(self):
    return sublime.active_window().active_view().settings().get('GoTools', {})

  # Returns setting with key, preferring project settings over plugin settings
  # and using default if neither is found. Key values with 0 length when
  # converted to a string are treated as None.
  def get_setting(self, key, default = None):
    val = self.project_settings.get(key, '')
    if len(str(val)) > 0:
      return val
    val = self.plugin_settings.get(key, '')
    if len(str(val)) > 0:
      return val
    return default

  # Reloads the plugin settings file from disk and validates required setings.
  def refresh(self):
    # Load settings from disk.
    self.plugin_settings = sublime.load_settings("GoTools.sublime-settings")

    # Validate properties.
    if self.gopath is None or len(self.gopath) == 0:
      raise Exception("GoTools requires either the `gopath` setting or the GOPATH environment variable to be s")
    if not self.goroot or not self.goarch or not self.goos or not self.go_tools:
      raise Exception("GoTools couldn't find Go runtime information")

    print("GoTools: configuration updated:\n\tgopath={0}\n\tgoroot={1}\n\tpath={2}\n\tdebug_enabled={3}".format(self.gopath, self.goroot, self.ospath, self.debug_enabled))

  # Project > Plugin > Shell env > OS env > go env
  @property
  def gopath(self):
    gopath = self.get_setting('gopath', self.env["GOPATH"])
    # Support 'gopath' expansion in project settings.
    if 'gopath' in self.project_settings:
      sub = self.plugin_settings.get('gopath', '')
      if len(sub) == 0:
        sub = self.env['GOPATH']
      gopath = self.project_settings['gopath'].replace('${gopath}', sub)
    return gopath

  @property
  def goroot(self):
    return self.get_setting('goroot', self.env["GOROOT"])

  @property
  def ospath(self):
    return self.get_setting('path', self.env["PATH"])

  @property
  def goarch(self):
    return self.env["GOHOSTARCH"]

  @property
  def goos(self):
    return self.env["GOHOSTOS"]

  @property
  def go_tools(self):
    return self.env["GOTOOLDIR"]

  @property
  def gorootbin(self):
    # The GOROOT bin directory is namespaced with the GOOS and GOARCH.
    return os.path.join(self.goroot, "bin", self.gohostosarch)

  @property
  def golibpath(self):
    libpath = []
    arch = "{0}_{1}".format(self.goos, self.goarch)
    libpath.append(os.path.join(self.goroot, "pkg", self.gohostosarch))
    for p in self.gopath.split(":"):
      libpath.append(os.path.join(p, "pkg", arch))
    return ":".join(libpath)

  @property
  def gohostosarch(self):
    return "{0}_{1}".format(self.goos, self.goarch)

  @property
  def debug_enabled(self):
    return self.get_setting("debug_enabled")

  @property
  def format_on_save(self):
    return self.get_setting("format_on_save")

  @property
  def format_backend(self):
    return self.get_setting("format_backend")

  @property
  def autocomplete(self):
    return self.get_setting("autocomplete")

  @property
  def goto_def_backend(self):
    return self.get_setting("goto_def_backend")

  @property
  def project_package(self):
    return self.get_setting("project_package")

  @property
  def build_packages(self):
    return self.get_setting("build_packages", [])

  @property
  def test_packages(self):
    return self.get_setting("test_packages", [])

  @property
  def tagged_test_tags(self):
    return self.get_setting("tagged_test_tags", [])

  @property
  def tagged_test_packages(self):
    return self.get_setting("tagged_test_packages", [])

  @property
  def verbose_tests(self):
    return self.get_setting("verbose_tests", False)

  @property
  def test_timeout(self):
    return self.get_setting("test_timeout", None)

  # Load PATH, GOPATH, GOROOT, and anything `go env` can provide. Use the
  # precedence order: Login shell > OS env > go env. The environment is
  # returned as a dict.
  #
  # Raises an exception if PATH can't be resolved or if `go env` fails.
  @staticmethod
  def create_environment():
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
      stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE, startupinfo=si, env=cmdenv).communicate()
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

    print("GoTools: using environment: {0}".format(str(env)))
    return env

  # Returns the absolute path to the go binary found on path. Raises an
  # exception if go can't be found.
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
