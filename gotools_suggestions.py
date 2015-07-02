import sublime
import sublime_plugin
import json
import os

from .gotools_util import Buffers
from .gotools_util import GoBuffers
from .gotools_util import Logger
from .gotools_util import ToolRunner
from .gotools_settings import GoToolsSettings

class GotoolsSuggestions(sublime_plugin.EventListener):
  CLASS_SYMBOLS = {
    "func": "ƒ",
    "var": "ν",
    "type": "ʈ",
    "package": "ρ"
  }

  def on_query_completions(self, view, prefix, locations):
    if not GoBuffers.is_go_source(view): return

    settings = GoToolsSettings()
    logger = Logger(settings)
    runner = ToolRunner(settings, logger)

    if not settings.autocomplete: return

    # set the lib-path for gocode's lookups
    _, _, rc = runner.run("gocode", ["set", "lib-path", GotoolsSuggestions.gocode_libpath(settings)])

    suggestionsJsonStr, stderr, rc = runner.run("gocode", ["-f=json", "autocomplete", 
      str(Buffers.offset_at_cursor(view)[0])], stdin=Buffers.buffer_text(view))

    # TODO: restore gocode's lib-path

    suggestionsJson = json.loads(suggestionsJsonStr)

    logger.log("DEBUG: gocode output: " + suggestionsJsonStr)

    if rc != 0:
      logger.status("no completions found: " + str(e))
      return []
    
    if len(suggestionsJson) > 0:
      return ([GotoolsSuggestions.build_suggestion(j) for j in suggestionsJson[1]], sublime.INHIBIT_WORD_COMPLETIONS)
    else:
      return []

  @staticmethod
  def gocode_libpath(settings):
    libpath = []
    libpath.append(os.path.join(settings.goroot, "pkg", settings.goos + "_" + settings.goarch))

    for p in settings.gopath.split(":"):
      libpath.append(os.path.join(p, "pkg", settings.goos + "_" + settings.goarch))

    return ":".join(libpath)

  @staticmethod
  def build_suggestion(json):
    label = '{0: <30.30} {1: <40.40} {2}'.format(
      json["name"],
      json["type"],
      GotoolsSuggestions.CLASS_SYMBOLS.get(json["class"], "?"))
    return (label, json["name"])
