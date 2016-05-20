import sublime
import os
import re
import platform
import subprocess
import time
import threading
from functools import partial
from collections import namedtuple


from .gotools_settings import GoToolsSettings

class Buffers():
  @staticmethod
  def offset_at_row_col(view, row, col):
    point = view.text_point(row, col)
    select_region = sublime.Region(0, point)
    string_region = view.substr(select_region)
    buffer_region = bytearray(string_region, encoding="utf8")
    offset = len(buffer_region)
    return offset

  @staticmethod
  def buffer_text(view):
    file_text = sublime.Region(0, view.size())
    return view.substr(file_text).encode('utf-8')

  @staticmethod
  def offset_at_cursor(view):
    begin_row, begin_col = view.rowcol(view.sel()[0].begin())
    end_row, end_col = view.rowcol(view.sel()[0].end())

    return (Buffers.offset_at_row_col(view, begin_row, begin_col), Buffers.offset_at_row_col(view, end_row, end_col))

  @staticmethod
  def location_at_cursor(view):
    row, col = view.rowcol(view.sel()[0].begin())
    offsets = Buffers.offset_at_cursor(view)
    return (view.file_name(), row, col, offsets[0], offsets[1])

  @staticmethod
  def location_for_event(view, event):
    pt = view.window_to_text((event["x"], event["y"]))
    row, col = view.rowcol(pt)
    offset = Buffers.offset_at_row_col(view, row, col)
    return (view.file_name(), row, col, offset)

class GoBuffers():
  @staticmethod
  def func_name_at_cursor(view):
    func_regions = view.find_by_selector('meta.function')

    func_name = ""
    for r in func_regions:
      if r.contains(Buffers.offset_at_cursor(view)[0]):
        lines = view.substr(r).splitlines()
        match = re.match('func.*(Test.+)\(', lines[0])
        if match and match.group(1):
          func_name = match.group(1)
          break

    return func_name

  @staticmethod
  def is_go_source(view):
    return view.score_selector(0, 'source.go') != 0

class Logger():
  @staticmethod
  def log(msg):
    if GoToolsSettings.debug_enabled():
      print("GoTools: DEBUG: {0}".format(msg))

  @staticmethod
  def error(msg):
    print("GoTools: ERROR: {0}".format(msg))

  @staticmethod
  def status(msg):
    sublime.status_message("GoTools: " + msg)

class Panel():
  def __init__(self, window, result_file_regex, name):
    panel = window.create_output_panel(name)
    panel.set_read_only(True)
    panel.set_scratch(True)
    panel.settings().set("result_file_regex", result_file_regex)
    self.panel = panel
    self.name = name
    self.window = window

  def clear(self):
    self.panel.set_read_only(False)
    self.panel.run_command("select_all")
    self.panel.run_command("right_delete")
    self.panel.set_read_only(True)

  def append(self, chars):
    self.panel.set_read_only(False)
    self.panel.run_command('append', {'characters': chars, 'scroll_to_end': True})
    self.panel.set_read_only(True)

  def show(self):
    self.window.run_command("show_panel", {"panel": 'output.{name}'.format(name=self.name)})

  def log(self, msg):
    self.append('[{name}> {msg}]\n'.format(name=self.name, msg=msg))
