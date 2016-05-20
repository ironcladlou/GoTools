import sublime
import sublime_plugin
import re
import os
import time
import subprocess

from .gotools_util import Panel
from .gotools_util import Logger

from .gotools_settings import GoToolsSettings

class Builder():
  Panel = 'gotools.build'
  ErrorPattern = r'^(.*\.go):(\d+):()(.*)$'

  def __init__(self, window):
    self.window = window
    self.panel = Panel(window, Builder.ErrorPattern, Builder.Panel)

  def install(self, packages, clean=False):
    cmd = [GoToolsSettings.get_tool('go'), 'install'] + packages
    if clean:
      #cmd = [GoToolsSettings.instance().tool_path('go'), 'install', '-a'] + packages
      # TODO: go clean instead, -a is inappropriate unless building the stdlib
      pass
    project_path = GoToolsSettings.project_path()
    timeout = GoToolsSettings.build_timeout()
    self.panel.clear()
    self.panel.show()
    self.panel.log('installing {package} (timeout: {timeout})'.format(package=' '.join(packages), timeout=timeout))
    p = subprocess.Popen(
      cmd,
      cwd=project_path,
      env={
        'GOPATH': GoToolsSettings.gopath(),
        'GOROOT': GoToolsSettings.goroot()
      },
      shell=False,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT
    )
    # TODO: this is reliant on the go timeout; readline could block forever
    # TODO: fix timeouts
    for line in iter(p.stdout.readline, b''):
      decoded = line.decode("utf-8")
      # Expand relative paths from the project path
      match = re.match(r'^(.*\.go)(:\d+:.*)$', decoded)
      if match:
        relative_path = match.group(1)
        decoded = '{0}{1}\n'.format(os.path.normpath(os.path.join(project_path, relative_path)), match.group(2))
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
    packages = GoToolsSettings.project_packages()
    clean = kwargs.get('clean') or False
    sublime.set_timeout_async(lambda: Builder(self.window).install(packages=packages, clean=clean))
