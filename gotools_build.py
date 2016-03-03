import sublime
import sublime_plugin
import re
import os
import time
import subprocess

from .gotools_util import Panel

from .gotools_settings import GoToolsSettings

class Builder():
  Panel = 'gotools.build'
  ErrorPattern = r'^(.*\.go):(\d+):()(.*)$'

  def __init__(self, window):
    self.window = window
    self.panel = Panel(window, Builder.ErrorPattern, Builder.Panel)

  def install(self, packages):
    cmd = [GoToolsSettings.instance().tool_path('go'), 'install'] + packages
    project_path = GoToolsSettings.instance().get('project_path')
    timeout = GoToolsSettings.instance().get('build_timeout')
    self.panel.clear()
    self.panel.show()
    for package in packages:
      self.panel.log('installing {package}'.format(package=package))
    self.panel.log('timeout: {timeout}s'.format(timeout=timeout))
    p = subprocess.Popen(
      cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
      env=GoToolsSettings.instance().tool_env(), startupinfo=GoToolsSettings.instance().tool_startupinfo(), cwd=project_path)
    # TODO: this is reliant on the go timeout; readline could block forever
    # TODO: fix timeouts
    for line in iter(p.stdout.readline, b''):
      decoded = line.decode("utf-8")
      # Expand relative paths from the project path
      match = re.match(r'^(.*\.go)(:\d+:.*)$', decoded)
      if match:
        decoded = '{0}{1}\n'.format(os.path.normpath(os.path.join(project_path, match.group(1))), match.group(2))
      self.panel.append(decoded)
    start = time.time()
    p.wait(timeout=timeout)
    elapsed = round(time.time() - start)
    self.panel.log("finished install (exited {rc} in {elapsed} seconds)".format(rc=p.returncode, elapsed=elapsed))

class GotoolsToggleBuildOutput(sublime_plugin.WindowCommand):
  def run(self):
    self.window.run_command("show_panel", {"panel": 'output.{name}'.format(name=Builder.Panel)})

class GotoolsInstall(sublime_plugin.WindowCommand):
  def run(self, *args, **kwargs):
    sublime.set_timeout_async(lambda: Builder(self.window).install(GoToolsSettings.instance().get('install_packages')))
