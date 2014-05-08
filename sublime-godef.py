import sublime, sublime_plugin, subprocess, os, locale

class GodefCommand(sublime_plugin.WindowCommand):
  def run(self):
    settings = sublime.load_settings("sublime-godef.sublime-settings")
    self.gopath = settings.get("gopath", os.getenv('GOPATH'))

    if self.gopath is None:
      print("ERROR: no GOPATH defined")
      return

    print("using gopath", self.gopath)

    view = self.window.active_view()
    row, col = view.rowcol(view.sel()[0].begin())

    self.offset = view.text_point(row, col)
    self.filename = view.file_name()
    
    sublime.set_timeout_async(self.godef, 0)

  def godef(self):
    try:
      args = [
        os.path.join(self.gopath, "bin", "godef"),
        "-f",
        self.filename,
        "-o",
        str(self.offset)
      ]

      print("spawning", " ".join(args))

      env = os.environ.copy()
      env["GOPATH"] = self.gopath
      output = subprocess.check_output(args, stderr=subprocess.STDOUT, env=env)
    except subprocess.CalledProcessError as e:
      print("no definition found")
    else:
      location = output.decode("utf-8").rstrip().split(":")

      file = location[0]
      row = int(location[1])
      col = int(location[2])

      print("opening definition at " + file + ":" + str(row) + ":" + str(col))
      view = self.window.open_file(file)
      pt = view.text_point(row, col)
      view.sel().clear()
      view.sel().add(sublime.Region(pt))
      view.show(pt)
