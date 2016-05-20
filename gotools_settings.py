import sublime
import os
import platform
import re
import subprocess
import tempfile
import threading

class GoToolsSettings():
  @classmethod
  def plugin_settings(cls):
    return sublime.load_settings('GoTools.sublime-settings')

  @classmethod
  def project_settings(cls):
    return sublime.active_window().active_view().settings().get('GoTools', {})

  # Returns setting with key, preferring project settings over plugin settings
  # and using default if neither is found. Key values with 0 length when
  # converted to a string are treated as None.
  @classmethod
  def get_setting(cls, key, default = None):
    val = cls.project_settings().get(key, '')
    if len(str(val)) > 0:
      return val
    val = cls.plugin_settings().get(key, '')
    if len(str(val)) > 0:
      return val
    return default

  @classmethod
  def project_path(cls):
    project_file_dir = '.'
    project_filename = sublime.active_window().project_file_name()
    if project_filename and len(project_filename) > 0:
      project_file_dir = os.path.dirname(project_filename)
    project_path = cls.get_setting('project_path').replace('${project_file_dir}', project_file_dir)
    return os.path.abspath(os.path.normpath(project_path))

  @classmethod
  def project_packages(cls):
    return cls.get_setting('project_packages', [])

  @classmethod
  def build_timeout(cls):
    return cls.get_setting('build_timeout', 180)

  @classmethod
  def gopath(cls):
    return cls.get_setting('gopath', '')

  @classmethod
  def goroot(cls):
    return cls.get_setting('goroot', '')

  @classmethod
  def tool_paths(cls):
    return cls.get_setting('tool_paths', '')

  @classmethod
  def debug_enabled(cls):
    return cls.get_setting('debug_enabled', False)

  @classmethod
  def format_on_save(cls):
    return cls.get_setting('format_on_save', False)

  @classmethod
  def format_backend(cls):
    return cls.get_setting('format_backend', 'gofmt')

  @classmethod
  def autocomplete(cls):
    return cls.get_setting('autocomplete', False)

  @classmethod
  def goto_def_backend(cls):
    return cls.get_setting('goto_def_backend', 'godef')

  @classmethod
  def verbose_tests(cls):
    return cls.get_setting('verbose_tests', True)

  @classmethod
  def test_timeout(cls):
    return cls.get_setting('test_timeout', 60)   

  @classmethod
  def get_tool(cls, name):
    toolpath = None
    if platform.system() == "Windows":
      name = name + ".exe"
    for path in cls.tool_paths():
      candidate = os.path.join(path, name)
      if os.path.isfile(candidate):
        toolpath = candidate
        break

    if not toolpath:
      raise Exception("couldn't find tool '{0}' in any of:\n{1}".format(name, "\n".join(cls.tool_paths)))
    return toolpath
