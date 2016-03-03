import sublime
import os
import platform
import re
import subprocess
import tempfile
import threading

def plugin_loaded():
  GoToolsSettings.refresh()

def plugin_unloaded():
  try:
    GoToolsSettings.plugin_settings.clear_on_change('gopath')
    GoToolsSettings.plugin_settings.clear_on_change('project_path')
    print('GoTools: Unloaded.')
  except AttributeError:
    pass

class GoToolsSettings():
  lock = threading.RLock()
  settings = None

  @classmethod
  def instance(cls):
    try:
      cls.lock.acquire()
      if not cls.settings:
        cls.settings = GoToolsSettings()
      return cls.settings
    finally:
      cls.lock.release()

  @classmethod
  def refresh(cls):
    try:
      cls.lock.acquire()
      cls.settings = GoToolsSettings()
    finally:
      cls.lock.release()

  def __init__(self):
    try:
      self.plugin_settings = sublime.load_settings('GoTools.sublime-settings')
      self.env = self.create_environment()
      
      if not self.get('gopath') or len(self.get('gopath')) == 0:
        print("GoTools: ERROR: no GOPATH is configured (using the `gopath` setting or the GOPATH environment variable)")
        return
      if not self.get('goroot') or not self.get('goarch') or not self.get('goos') or not self.get('go_tools'):
        print("GoTools: ERROR: couldn't find the Go installation (using the `goroot` setting or GOROOT environment variable)")
        return

      print("GoTools: Initialized successfully.\n\tgopath={gopath}\n\tgoroot={goroot}\n\tpath={ospath}\n\tproject_path={project_path}\n\tenv:{env}\n\tdebug_enabled={debug_enabled}\n".format(
        gopath=self.get('gopath'),
        goroot=self.get('goroot'),
        ospath=self.get('ospath'),
        debug_enabled=self.get('debug_enabled'),
        env=str(self.env),
        project_path=self.get('project_path')
      ))
      self.plugin_settings.add_on_change('gopath', GoToolsSettings.refresh)
      self.plugin_settings.add_on_change('project_path', GoToolsSettings.refresh)
    except Exception as e:
      print('GoTools: ERROR: Initialization failure: {err}'.format(err=str(e)))

  # There's no direct access to project settings, so load them from the active
  # view every time. This doesn't seem ideal.
  def project_settings(self):
    return sublime.active_window().active_view().settings().get('GoTools', {})

  # Returns setting with key, preferring project settings over plugin settings
  # and using default if neither is found. Key values with 0 length when
  # converted to a string are treated as None.
  def get_setting(self, key, default = None):
    val = self.project_settings().get(key, '')
    if len(str(val)) > 0:
      return val
    val = self.plugin_settings.get(key, '')
    if len(str(val)) > 0:
      return val
    return default

  def get(self, key):
    if key == 'project_path':
      return self.get_project_path()
    if key == 'install_packages':
      return self.get_setting('install_packages', [])
    if key == 'build_timeout':
      return self.get_setting('build_timeout', 180)
    if key == 'gopath':
      return self.get_gopath()
    if key == 'goroot':
      return self.get_setting('goroot', self.env["GOROOT"])
    if key == 'ospath':
      return self.get_setting('path', self.env["PATH"])
    if key == 'goarch':
      return self.env["GOHOSTARCH"]
    if key == 'goos':
      return self.env["GOHOSTOS"]
    if key == 'go_tools':
      return self.env["GOTOOLDIR"]
    if key == 'gorootbin':
      # The GOROOT bin directory is namespaced with the GOOS and GOARCH.
      return os.path.join(self.get('goroot'), 'bin', self.get('gohostosarch'))
    if key == 'golibpath':
      return self.get_golibpath()
    if key == 'gohostosarch':
      return "{0}_{1}".format(self.get('goos'), self.get('goarch'))
    if key == 'debug_enabled':
      return self.get_setting("debug_enabled")
    if key == 'format_on_save':
      return self.get_setting("format_on_save")
    if key == 'format_backend':
      return self.get_setting("format_backend")
    if key == 'autocomplete':
      return self.get_setting("autocomplete")
    if key == 'goto_def_backend':
      return self.get_setting("goto_def_backend")
    if key == 'verbose_tests':
      return self.get_setting("verbose_tests", False)
    if key == 'test_timeout':
      return self.get_setting('test_timeout', None)

  # Project > Plugin > Shell env > OS env > go env
  def get_gopath(self):
    gopath = self.get_setting('gopath', self.env["GOPATH"])
    # Support 'gopath' expansion in project settings.
    if 'gopath' in self.project_settings():
      sub = self.plugin_settings.get('gopath', '')
      if len(sub) == 0:
        sub = self.env['GOPATH']
      gopath = self.project_settings()['gopath'].replace('${gopath}', sub)
      gopath = gopath.replace('${project_file_dir}', self.get_project_file_dir())

    expanded = []
    for path in gopath.split(':'):
      if path[0] == '.':
        print('joining project_path={pp} and gopath element={p}\n'.format(pp=self.get('project_path'), p=path))
        expanded.append(os.path.normpath(os.path.join(self.get('project_path'), path)))
      else:
        expanded.append(os.path.normpath(path))
    return ":".join(expanded)    

  def get_golibpath(self):
    libpath = []
    arch = "{0}_{1}".format(self.get('goos'), self.get('goarch'))
    libpath.append(os.path.join(self.get('goroot'), 'pkg', self.get('gohostosarch')))
    for p in self.get('gopath').split(':'):
      libpath.append(os.path.join(p, "pkg", arch))
    return ":".join(libpath)

  def get_project_path(self):
    project_path = self.get_setting('project_path').replace('${project_file_dir}', self.get_project_file_dir())
    return os.path.abspath(os.path.normpath(project_path))

  def get_project_file_dir(self):
    project_filename = sublime.active_window().project_file_name()
    if project_filename and len(project_filename) > 0:
      return os.path.dirname(project_filename)
    return '.'

  # Load PATH, GOPATH, GOROOT, and anything `go env` can provide. Use the
  # precedence order: Login shell > OS env > go env. The environment is
  # returned as a dict.
  #
  # Raises an exception if PATH can't be resolved or if `go env` fails.
  def create_environment(self):
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
    gobinary = self.find_go_binary(env['PATH'])

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
    return env

  # Returns the absolute path to the go binary found on path. Raises an
  # exception if go can't be found.
  def find_go_binary(self, path=""):
    goname = "go"
    if platform.system() == "Windows":
      goname = "go.exe"
    for segment in path.split(os.pathsep):
      candidate = os.path.join(segment, goname)
      if os.path.isfile(candidate):
        return candidate
    raise Exception("couldn't find the go binary in path: {0}".format(path))

  def tool_env(self):
    env = os.environ.copy()
    env["PATH"] = self.get('ospath')
    env["GOPATH"] = self.get('gopath')
    env["GOROOT"] = self.get('goroot')
    return env

  def tool_startupinfo(self):
    si = None
    if platform.system() == "Windows":
      si = subprocess.STARTUPINFO()
      si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return si

  def tool_path(self, tool):
    toolpath = None
    searchpaths = list(map(lambda x: os.path.join(x, 'bin'), self.get('gopath').split(os.pathsep)))
    for p in self.get('ospath').split(os.pathsep):
      searchpaths.append(p)
    searchpaths.append(os.path.join(self.get('goroot'), 'bin'))
    searchpaths.append(self.get('gorootbin'))

    if platform.system() == "Windows":
      tool = tool + ".exe"

    for path in searchpaths:
      candidate = os.path.join(path, tool)
      if os.path.isfile(candidate):
        toolpath = candidate
        break

    if not toolpath:
      raise Exception("couldn't find tool '{0}' in any of:\n{1}".format(tool, "\n".join(searchpaths)))

    return toolpath
